"""单标本危急值确认流程：复核、更正、确认凭据。"""


def make_run(client, profile="clean"):
    response = client.post("/api/runs", json={"profile": profile})
    assert response.status_code == 200
    return response.get_json()


def specimen(run, specimen_id):
    return next(item for item in run["rows"] if item["specimen_id"] == specimen_id)


def review(client, run_id, specimen_id, revision, comment="危急值已复核"):
    return client.post(f"/api/runs/{run_id}/specimens/{specimen_id}/review",
                       json={"expected_revision": revision, "comment": comment})


def issue(client, run_id, specimen_id, revision):
    return client.post(f"/api/runs/{run_id}/specimens/{specimen_id}/credential",
                       json={"expected_revision": revision})


def correct(client, run_id, specimen_id, revision, corrected):
    return client.post(f"/api/runs/{run_id}/specimens/{specimen_id}/correct",
                       json={"expected_revision": revision, "corrected": corrected})


def test_specimens_list_starts_pending(client):
    run = make_run(client)
    listing = client.get(f"/api/runs/{run['run_id']}/specimens").get_json()
    assert len(listing["items"]) == len(run["rows"])
    assert all(item["status"] == "PENDING" and item["revision"] == 0 for item in listing["items"])


def test_reviewed_specimen_can_issue_credential_individually(client):
    run = make_run(client)
    target = specimen(run, "P1")
    response = review(client, run["run_id"], "P1", 0)
    assert response.status_code == 200
    state = response.get_json()
    assert state["status"] == "REVIEWED"
    assert state["revision"] == 1

    credential = issue(client, run["run_id"], "P1", 1)
    assert credential.status_code == 200
    artifact = credential.get_json()
    assert artifact["schema"] == "workbench-confirmation/v1"
    assert artifact["run_id"] == run["run_id"]
    assert artifact["specimen_id"] == "P1"
    assert artifact["specimen"]["verdict"] == target["verdict"]
    assert len(artifact["credential_id"]) == 32
    assert len(artifact["artifact_sha256"]) == 64


def test_unreviewed_specimen_cannot_issue(client):
    run = make_run(client)
    response = issue(client, run["run_id"], "P1", 0)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOT_REVIEWED"


def test_credential_retry_is_idempotent_and_kept_verbatim(client):
    run = make_run(client)
    review(client, run["run_id"], "P1", 0)
    first = issue(client, run["run_id"], "P1", 1).get_json()
    second = issue(client, run["run_id"], "P1", 1).get_json()
    # 重试不重新生成凭据：编号、时间、摘要原样一致
    assert first == second
    fetched = client.get(f"/api/runs/{run['run_id']}/specimens/P1/credential").get_json()
    assert fetched == first


def test_equivalent_unit_correction_keeps_review_valid(client):
    # P4 原始录入即 mg/dL，换算后 5.0 mmol/L；换个单位重新表达同一读数，
    # 换算结果与判定都不变，原复核应保持有效。
    run = make_run(client)
    before = specimen(run, "P4")
    review(client, run["run_id"], "P4", 0)

    same_reading = {
        "specimen_id": "P4", "patient_id": "A4", "age": "28", "sex": "F",
        "analyte": "GLU", "value": str(before["value"]), "unit": "mmol/L",
        "prev_value": str(before.get("prev_value", "")), "hours": "24",
    }
    response = correct(client, run["run_id"], "P4", 1, same_reading)
    assert response.status_code == 200
    state = response.get_json()
    assert state["status"] == "REVIEWED"
    assert state["revision"] == 2

    refreshed = client.get(f"/api/runs/{run['run_id']}/specimens").get_json()
    updated = next(item for item in refreshed["items"] if item["specimen_id"] == "P4")
    assert updated["value"] == before["value"]
    assert updated["verdict"] == before["verdict"]

    # 原复核仍有效，带新版本号即可签发
    credential = issue(client, run["run_id"], "P4", 2)
    assert credential.status_code == 200


def test_reading_change_invalidates_review(client):
    run = make_run(client)
    review(client, run["run_id"], "P1", 0)
    changed = {
        "specimen_id": "P1", "patient_id": "A1", "age": "40", "sex": "M",
        "analyte": "GLU", "value": "7.8", "unit": "mmol/L",
        "prev_value": "5.0", "hours": "24",
    }
    response = correct(client, run["run_id"], "P1", 1, changed)
    assert response.status_code == 200
    state = response.get_json()
    assert state["status"] == "PENDING"
    assert state["revision"] == 2

    # 失效复核不能签发
    blocked = issue(client, run["run_id"], "P1", 2)
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "NOT_REVIEWED"

    # 重审后恢复可签发
    review(client, run["run_id"], "P1", 2)
    assert issue(client, run["run_id"], "P1", 3).status_code == 200


def test_verdict_change_invalidates_review_even_with_same_reading_shape(client):
    # 同一读数放到不同参考区间（改年龄）会改变判定，必须重审
    run = make_run(client)
    review(client, run["run_id"], "P2", 0)
    changed = {
        "specimen_id": "P2", "patient_id": "A2", "age": "20", "sex": "M",
        "analyte": "HGB", "value": "125", "unit": "g/L",
        "prev_value": "125", "hours": "24",
    }
    state = correct(client, run["run_id"], "P2", 1, changed).get_json()
    assert state["status"] == "PENDING"


def test_stale_correction_and_issuance_are_rejected(client):
    run = make_run(client)
    review(client, run["run_id"], "P1", 0)
    changed = {
        "specimen_id": "P1", "patient_id": "A1", "age": "40", "sex": "M",
        "analyte": "GLU", "value": "7.8", "unit": "mmol/L",
        "prev_value": "5.0", "hours": "24",
    }
    accepted = correct(client, run["run_id"], "P1", 1, changed)
    assert accepted.status_code == 200
    # 读数变化后复核失效，过时的复核（rev 1）不能再签发
    stale_issue = issue(client, run["run_id"], "P1", 1)
    assert stale_issue.status_code == 409
    assert stale_issue.get_json()["code"] in {"STALE_REVIEW", "NOT_REVIEWED"}
    # 过时版本号的更正同样被拒
    stale_correct = correct(client, run["run_id"], "P1", 1, changed)
    assert stale_correct.status_code == 409
    assert stale_correct.get_json()["code"] == "STALE_REVIEW"

    # 读数/判定不变的等价更正会保留 REVIEWED，此时用旧版本号签发必须被 STALE_REVIEW 拦截，
    # 即“更正与签发同时提交时，过时的复核不能签发”。
    run2 = make_run(client, "dirty")
    review(client, run2["run_id"], "P1", 0)
    p1 = specimen(run2, "P1")
    equivalent = {
        "specimen_id": "P1", "patient_id": "A1", "age": "40", "sex": "M",
        "analyte": "GLU", "value": str(p1["value"]), "unit": "mmol/L",
        "prev_value": str(p1.get("prev_value", "")), "hours": "24",
    }
    correction = correct(client, run2["run_id"], "P1", 1, equivalent)
    assert correction.status_code == 200
    assert correction.get_json()["status"] == "REVIEWED"
    stale = issue(client, run2["run_id"], "P1", 1)
    assert stale.status_code == 409
    assert stale.get_json()["code"] == "STALE_REVIEW"


def test_sealed_credential_blocks_further_changes(client):
    run = make_run(client)
    review(client, run["run_id"], "P1", 0)
    issue(client, run["run_id"], "P1", 1)

    changed = {
        "specimen_id": "P1", "patient_id": "A1", "age": "40", "sex": "M",
        "analyte": "GLU", "value": "7.8", "unit": "mmol/L",
        "prev_value": "5.0", "hours": "24",
    }
    correction = correct(client, run["run_id"], "P1", 1, changed)
    assert correction.status_code == 409
    assert correction.get_json()["code"] == "CREDENTIAL_SEALED"

    re_review = review(client, run["run_id"], "P1", 1)
    assert re_review.status_code == 409
    assert re_review.get_json()["code"] == "CREDENTIAL_SEALED"


def test_invalid_correction_is_rejected_without_state_change(client):
    run = make_run(client)
    review(client, run["run_id"], "P1", 0)
    bad = {
        "specimen_id": "P1", "patient_id": "A1", "age": "40", "sex": "M",
        "analyte": "GLU", "value": "-1", "unit": "mmol/L",
        "prev_value": "5.0", "hours": "24",
    }
    response = correct(client, run["run_id"], "P1", 1, bad)
    assert response.status_code == 422
    assert response.get_json()["code"] == "SPECIMEN_INVALID"
    # 原复核与版本号不受影响
    state = review(client, run["run_id"], "P1", 1)  # 重复复核推进版本
    assert state.status_code == 200


def test_critical_value_from_dirty_run_follows_same_flow(client):
    run = make_run(client, "dirty")
    listing = client.get(f"/api/runs/{run['run_id']}/specimens").get_json()
    critical = next(item for item in listing["items"] if item["verdict"] == "REJECT")
    assert critical["specimen_id"] == "P7"
    review(client, run["run_id"], "P7", 0, comment="危急值 30 mmol/L 已电话复核")
    artifact = issue(client, run["run_id"], "P7", 1).get_json()
    assert artifact["specimen"]["verdict"] == "REJECT"
    assert artifact["review"]["comment"] == "危急值 30 mmol/L 已电话复核"


def test_unknown_specimen_returns_404(client):
    run = make_run(client)
    response = review(client, run["run_id"], "NOPE", 0)
    assert response.status_code == 404
    assert response.get_json()["code"] == "SPECIMEN_NOT_FOUND"


def test_credential_fingerprint_matches_current_row(client):
    run = make_run(client)
    review(client, run["run_id"], "P1", 0)
    artifact = issue(client, run["run_id"], "P1", 1).get_json()
    from app.specimen.policy import content_fingerprint
    assert artifact["specimen"]["content_fingerprint"] == content_fingerprint(specimen(run, "P1"))
