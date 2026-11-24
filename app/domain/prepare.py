from app.catalog import SPEC
from app.domain.helpers import D, DAY, I, M, TS, optional
from app.intake.normalize import canonical


PARSERS = {
    "money": lambda value, code: M(value, code),
    "decimal": lambda value, code: D(value, code),
    "decimal_optional": lambda value, code: optional(D, value, code),
    "int": lambda value, code: I(value, code),
    "int_positive": lambda value, code: positive(I(value, code)),
    "date": lambda value, code: DAY(value, code),
    "date_optional": lambda value, code: optional(DAY, value, code),
    "datetime": lambda value, code: TS(value, code),
}


def positive(value):
    if value <= 0:
        raise ValueError("BAD_POSITIVE")
    return value


def _typed(rows):
    typed, issues = [], []
    for raw in rows:
        item = dict(raw)
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            for field, kind in SPEC["types"].items():
                code = "INVALID_" + field.upper()
                item[field] = PARSERS[kind](item.get(field), code)
            typed.append(item)
        except ValueError as exc:
            issues.append({"line": raw.get("_line", 0), "key": raw.get(SPEC["key"], ""), "code": str(exc)})
    return typed, issues


def prepare_rows(rows):
    typed, issues = _typed(rows)
    rows = typed
    items = []
    for item in typed:
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            sex = item["sex"].upper()
            if sex not in {"M", "F"}:
                raise ValueError("BAD_SEX")
            unit = item["unit"].upper()
            if item["analyte"].upper() == "GLU":
                if unit == "MG/DL":
                    item["value"] = item["value"] / D("18.0", "BAD_UNIT")
                    if item["prev_value"] is not None:
                        item["prev_value"] = item["prev_value"] / D("18.0", "BAD_UNIT")
                elif unit != "MMOL/L":
                    raise ValueError("BAD_UNIT")
            elif item["analyte"].upper() == "HGB":
                if unit == "G/DL":
                    item["value"] *= D("10", "BAD_UNIT")
                    if item["prev_value"] is not None:
                        item["prev_value"] *= D("10", "BAD_UNIT")
                elif unit != "G/L":
                    raise ValueError("BAD_UNIT")
            elif item["analyte"].upper() != "PLT":
                raise ValueError("BAD_ANALYTE")
            elif unit != "10^9/L":
                raise ValueError("BAD_UNIT")
            if not 0 <= item["age"] <= 125:
                raise ValueError("BAD_AGE")
            if item["value"] <= 0 or (item["prev_value"] is not None and item["prev_value"] <= 0):
                raise ValueError("BAD_VALUE")
            if item.get("hours") is not None and item["hours"] < 0:
                raise ValueError("BAD_HOURS")
            items.append(item)
        except ValueError as exc:
            issues.append({"line": item.get("_line", 0), "key": item.get(SPEC["key"], ""), "code": str(exc)})
    return items, issues
