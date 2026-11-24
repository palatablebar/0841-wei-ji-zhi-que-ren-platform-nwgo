from app.catalog import SPEC
from app.domain.calculate import calculate_rows
from app.domain.decision import decide_rows
from app.domain.jsonio import jsonable
from app.domain.prepare import prepare_rows
from app.evidence.manifest import stable_digest

# 指纹只覆盖“换算后的读数”和“判定”。原始单位、原始值等仅影响录入形态的
# 字段不参与指纹：单位换算后读数与判定不变时，同一标本的复核仍然有效。
FINGERPRINT_FIELDS = (
    SPEC["key"], "patient_id", "analyte", "value", "unit", "prev_value",
    "low", "high", "metric", "verdict", "reason",
)


def content_fingerprint(row):
    """标本当前内容的稳定指纹，覆盖标准化读数与危急判定。"""
    material = jsonable({field: row.get(field) for field in FINGERPRINT_FIELDS})
    return stable_digest(material)


def reprocess(raw_row):
    """对单条更正后的标本原始记录重跑整理、计算与判定。

    返回 (标准化结果行, 问题码)。整理层拒收时结果行为 None。
    """
    raw = dict(raw_row)
    raw.setdefault("_line", 0)
    prepared, prepare_issues = prepare_rows([raw])
    if not prepared:
        code = prepare_issues[0]["code"] if prepare_issues else "SPECIMEN_INVALID"
        return None, code
    results = decide_rows(calculate_rows(prepared))
    return results[0], None
