from flask import Blueprint, abort, jsonify, request, send_file

from app.catalog import SPEC
from app.config import SAMPLES
from app.errors import DomainIssue
from app.evidence.render import render
from app.review.service import approve, create_run, serialize
from app.service import pipeline
from app.specimen import service as specimen_service


api = Blueprint("api", __name__)
STAGE_INDEX = {"intake": 1, "prepare": 2, "calculate": 3, "decision": 4, "reconcile": 5}


def store():
    from flask import current_app
    return current_app.extensions["runs"]


@api.get("/api/catalog")
def catalog():
    return jsonify(code=SPEC["code"], name=SPEC["name"], actor=SPEC["actor"], rule=SPEC["rule"],
                   rule_short=SPEC["rule_short"],
                   stages=[{"id": item, "name": name} for item, name in zip(
                       ["intake", "prepare", "calculate", "decision", "reconcile", "review", "evidence"],
                       SPEC["stages"])],
                   chart=SPEC["chart"], result_columns=SPEC["result_columns"],
                   columns=SPEC["columns"], samples=["dirty", "clean"])


@api.post("/api/stages/<stage_id>")
def stage(stage_id):
    if stage_id not in STAGE_INDEX:
        raise DomainIssue("STAGE_UNKNOWN", 404)
    data = request.get_json(silent=True) or {}
    profile = data.get("profile", "dirty")
    upto = SPEC["stages"][STAGE_INDEX[stage_id] - 1]
    return jsonify(pipeline(profile, upto=upto))


@api.post("/api/runs")
def create():
    data = request.get_json(silent=True) or {}
    profile = data.get("profile", "dirty")
    payload = pipeline(profile)
    return jsonify(create_run(store(), payload))


@api.get("/api/runs/<run_id>")
def get_run(run_id):
    run = serialize(store().get(run_id))
    if not run:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    return jsonify(run)


@api.post("/api/runs/<run_id>/review")
def review(run_id):
    data = request.get_json(silent=True) or {}
    if "decision" not in data or "expected_revision" not in data:
        raise DomainIssue("BAD_REQUEST")
    return jsonify(approve(store(), run_id, data["decision"], data.get("comment", ""), int(data["expected_revision"])))


@api.get("/api/runs/<run_id>/evidence")
def evidence(run_id):
    run = serialize(store().get(run_id))
    return jsonify(render(run))


@api.get("/api/runs/<run_id>/specimens")
def specimens(run_id):
    return jsonify(specimen_service.list_confirmations(store(), run_id))


@api.post("/api/runs/<run_id>/specimens/<specimen_id>/review")
def specimen_review(run_id, specimen_id):
    data = request.get_json(silent=True) or {}
    if "expected_revision" not in data:
        raise DomainIssue("BAD_REQUEST")
    return jsonify(specimen_service.review_specimen(
        store(), run_id, specimen_id, data.get("comment", ""), int(data["expected_revision"])))


@api.post("/api/runs/<run_id>/specimens/<specimen_id>/correct")
def specimen_correct(run_id, specimen_id):
    data = request.get_json(silent=True) or {}
    if "expected_revision" not in data or not isinstance(data.get("corrected"), dict):
        raise DomainIssue("BAD_REQUEST")
    return jsonify(specimen_service.correct_specimen(
        store(), run_id, specimen_id, data["corrected"], int(data["expected_revision"])))


@api.post("/api/runs/<run_id>/specimens/<specimen_id>/credential")
def specimen_credential(run_id, specimen_id):
    data = request.get_json(silent=True) or {}
    if "expected_revision" not in data:
        raise DomainIssue("BAD_REQUEST")
    return jsonify(specimen_service.issue_credential(
        store(), run_id, specimen_id, int(data["expected_revision"])))


@api.get("/api/runs/<run_id>/specimens/<specimen_id>/credential")
def specimen_credential_get(run_id, specimen_id):
    return jsonify(specimen_service.get_credential(store(), run_id, specimen_id))


@api.get("/api/examples/<profile>")
def example(profile):
    if profile not in {"clean", "dirty"}:
        abort(404)
    return send_file(SAMPLES / f"{profile}.csv", as_attachment=True)
