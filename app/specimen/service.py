import json
import uuid
from datetime import datetime, timezone

from app.catalog import SPEC
from app.domain.jsonio import jsonable
from app.errors import DomainIssue
from app.evidence.manifest import stable_digest
from app.review.service import serialize
from app.specimen.policy import content_fingerprint, reprocess

# 批次结果行实际落库的字段，与 app.service.pipeline 的裁剪口径保持一致
ROW_FIELDS = {"label", "verdict", "reason", "metric", "limit", "status", "state", "breakdown"} \
    | set(SPEC["columns"]) | set(SPEC["result_columns"])


def _run(store, run_id):
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    return row


def _find_row(payload, specimen_id):
    for row in payload["rows"]:
        if row.get(SPEC["key"]) == specimen_id:
            return row
    raise DomainIssue("SPECIMEN_NOT_FOUND", 404)


def _refresh_summary(payload):
    summary = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
    for row in payload["rows"]:
        verdict = row.get("verdict", "REVIEW")
        summary[verdict] = summary.get(verdict, 0) + 1
    payload["summary"] = summary


def _state_view(store, run_id, specimen_id):
    state = store.get_specimen_state(run_id, specimen_id) or {
        "status": "PENDING", "revision": 0, "content_fingerprint": None,
        "comment": "", "reviewed_at": None,
    }
    state["credential"] = store.get_credential(run_id, specimen_id) is not None
    return state


def list_confirmations(store, run_id):
    _run(store, run_id)
    payload = json.loads(store.get(run_id)["payload"])
    states = {(item["specimen_id"]): item for item in store.list_specimen_states(run_id)}
    issued = store.credential_index(run_id)
    items = []
    for row in payload["rows"]:
        specimen_id = row.get(SPEC["key"])
        state = states.get(specimen_id)
        items.append({
            "specimen_id": specimen_id,
            "patient_id": row.get("patient_id"),
            "age": row.get("age"),
            "sex": row.get("sex"),
            "verdict": row.get("verdict"),
            "reason": row.get("reason"),
            "analyte": row.get("analyte"),
            "value": row.get("value"),
            "unit": row.get("unit"),
            "prev_value": row.get("prev_value"),
            "hours": row.get("hours"),
            "status": state["status"] if state else "PENDING",
            "revision": state["revision"] if state else 0,
            "comment": state["comment"] if state else "",
            "fingerprint": state["content_fingerprint"] if state else None,
            "credential": specimen_id in issued,
        })
    return {"run_id": run_id, "items": items}


def review_specimen(store, run_id, specimen_id, comment, expected_revision):
    _run(store, run_id)
    payload = json.loads(store.get(run_id)["payload"])
    row = _find_row(payload, specimen_id)
    fingerprint = content_fingerprint(row)
    state, problem = store.mark_reviewed(run_id, specimen_id, fingerprint,
                                         (comment or "").strip(), int(expected_revision))
    if problem == "sealed":
        raise DomainIssue("CREDENTIAL_SEALED", 409)
    if problem == "stale":
        raise DomainIssue("STALE_REVIEW", 409)
    return _state_view(store, run_id, specimen_id)


def correct_specimen(store, run_id, specimen_id, corrected, expected_revision):
    _run(store, run_id)
    payload = json.loads(store.get(run_id)["payload"])
    _find_row(payload, specimen_id)
    if not isinstance(corrected, dict) or not corrected.get(SPEC["key"]):
        raise DomainIssue("BAD_REQUEST")
    # 更正不允许改主键，避免“同标本”语义被绕过
    if str(corrected[SPEC["key"]]) != str(specimen_id):
        raise DomainIssue("SPECIMEN_KEY_MISMATCH", 400)
    reprocessed, issue = reprocess(corrected)
    if issue is not None:
        raise DomainIssue("SPECIMEN_INVALID", 422, detail=issue)
    new_row = jsonable({key: value for key, value in reprocessed.items() if key in ROW_FIELDS})
    fingerprint = content_fingerprint(reprocessed)
    # 先在事务外构造新批次载荷，再与复核状态在同一事务内落库
    new_payload = json.loads(json.dumps(payload, ensure_ascii=False))
    for index, row in enumerate(new_payload["rows"]):
        if row.get(SPEC["key"]) == specimen_id:
            new_payload["rows"][index] = new_row
            break
    _refresh_summary(new_payload)
    for point in new_payload.get("chart", []):
        if point.get("label") == specimen_id:
            point["value"] = float(reprocessed.get("metric") or 0)
            point["limit"] = float(reprocessed.get("limit") or 0)
    state, problem = store.correct_specimen(run_id, specimen_id, new_payload, fingerprint,
                                            int(expected_revision))
    if problem == "sealed":
        raise DomainIssue("CREDENTIAL_SEALED", 409)
    if problem == "stale":
        raise DomainIssue("STALE_REVIEW", 409)
    if problem == "missing":
        raise DomainIssue("RUN_NOT_FOUND", 404)
    return _state_view(store, run_id, specimen_id)


def issue_credential(store, run_id, specimen_id, expected_revision):
    _run(store, run_id)
    payload = json.loads(store.get(run_id)["payload"])
    row = _find_row(payload, specimen_id)
    fingerprint = content_fingerprint(row)
    run = serialize(store.get(run_id))
    credential_id = uuid.uuid4().hex
    artifact = {
        "schema": "workbench-confirmation/v1",
        "credential_id": credential_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "specimen_id": specimen_id,
        "project": run["project"],
        "rule": run["rule"],
        "profile": run["profile"],
        "source": run["source"],
        "specimen": {
            "patient_id": row.get("patient_id"),
            "analyte": row.get("analyte"),
            "value": row.get("value"),
            "unit": row.get("unit"),
            "verdict": row.get("verdict"),
            "reason": row.get("reason"),
            "content_fingerprint": fingerprint,
        },
        "review": {"status": "REVIEWED", "revision": int(expected_revision),
                   "comment": _review_comment(store, run_id, specimen_id)},
    }
    artifact["artifact_sha256"] = stable_digest(artifact)
    saved, problem = store.insert_credential(run_id, specimen_id, int(expected_revision),
                                             fingerprint, artifact)
    if problem == "duplicate":
        return saved
    if problem == "not_reviewed":
        raise DomainIssue("NOT_REVIEWED", 409)
    if problem == "stale":
        raise DomainIssue("STALE_REVIEW", 409)
    if problem == "superseded":
        raise DomainIssue("REVIEW_SUPERSEDED", 409)
    return saved


def _review_comment(store, run_id, specimen_id):
    state = store.get_specimen_state(run_id, specimen_id)
    return state["comment"] if state else ""


def get_credential(store, run_id, specimen_id):
    _run(store, run_id)
    record = store.get_credential(run_id, specimen_id)
    if record is None:
        raise DomainIssue("CREDENTIAL_NOT_FOUND", 404)
    return json.loads(record["artifact"])
