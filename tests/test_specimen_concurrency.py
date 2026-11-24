"""并发场景：更正与签发同时提交时，过时复核不能签发凭据。"""
import json
import threading

from app.review.store import Store
from app.specimen.policy import content_fingerprint
from app.specimen.service import issue_credential, review_specimen, correct_specimen
from app.errors import DomainIssue


def _run_id(store):
    from app.service import pipeline
    payload = pipeline("clean")
    row = store.create(payload["run_key"], "clean", payload)
    return row["id"]


def _corrected(value):
    return {
        "specimen_id": "P1", "patient_id": "A1", "age": "40", "sex": "M",
        "analyte": "GLU", "value": value, "unit": "mmol/L",
        "prev_value": "5.0", "hours": "24",
    }


def test_correction_and_issuance_race_keeps_credential_consistent(tmp_path):
    store = Store(str(tmp_path / "race.sqlite3"))
    run_id = _run_id(store)
    review_specimen(store, run_id, "P1", "首复核", 0)

    outcomes = {}

    def correct():
        # 更正方拿到的是复核后的 rev 1
        try:
            state = correct_specimen(store, run_id, "P1", _corrected("7.8"), 1)
            outcomes["correct"] = ("ok", state["status"], state["revision"])
        except DomainIssue as exc:
            outcomes["correct"] = ("blocked", exc.code)

    def issue():
        # 签发方同样拿着 rev 1，与更正同时提交
        try:
            artifact = issue_credential(store, run_id, "P1", 1)
            outcomes["issue"] = ("ok", artifact["credential_id"])
        except DomainIssue as exc:
            outcomes["issue"] = ("blocked", exc.code)

    threads = [threading.Thread(target=correct), threading.Thread(target=issue)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if outcomes["issue"][0] == "ok":
        # 签发先提交：凭据已留存，随后的更正必须被封存拦截，凭据内容对应原读数
        assert outcomes["correct"][0] == "blocked"
        assert outcomes["correct"][1] == "CREDENTIAL_SEALED"
        record = store.get_credential(run_id, "P1")
        assert record is not None
        assert json.loads(record["artifact"])["specimen"]["value"] == 5.2
    else:
        # 更正先提交：读数变化使复核失效，过时版本的签发不得出凭据
        assert outcomes["correct"][0] == "ok"
        assert outcomes["correct"][1] == "PENDING"
        assert outcomes["issue"][1] in {"STALE_REVIEW", "NOT_REVIEWED"}
        assert store.get_credential(run_id, "P1") is None
        # 重审后仍可正常签发，凭据对应更正后的读数
        review_specimen(store, run_id, "P1", "重新复核", 2)
        artifact = issue_credential(store, run_id, "P1", 3)
        assert artifact["specimen"]["value"] == 7.8


def test_parallel_issuance_creates_single_credential(tmp_path):
    store = Store(str(tmp_path / "parallel.sqlite3"))
    run_id = _run_id(store)
    review_specimen(store, run_id, "P1", "首复核", 0)

    artifacts = []
    errors = []

    def issue():
        try:
            artifacts.append(issue_credential(store, run_id, "P1", 1)["credential_id"])
        except DomainIssue as exc:
            errors.append(exc.code)

    threads = [threading.Thread(target=issue) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 无论多少个并发签发请求，只会生成一张凭据，其余请求原样拿到同一张
    assert len(artifacts) == 8
    assert len(set(artifacts)) == 1
    assert errors == []
