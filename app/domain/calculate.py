from datetime import date, timedelta
from app.catalog import SPEC
from app.domain.helpers import *  # noqa: F401,F403


def calculate_rows(items):
    out = []
    rows = items
    for item in items:
        analyte, sex, age = item["analyte"].upper(), item["sex"].upper(), item["age"]
        if analyte == "GLU":
            low, high, critical_low, critical_high = D("3.9", "R"), D("6.1", "R"), D("2.8", "R"), D("22.2", "R")
        elif analyte == "HGB":
            low, high = (D("130", "R"), D("175", "R")) if age >= 18 and sex == "M" else (D("115", "R"), D("150", "R"))
            critical_low, critical_high = D("70", "R"), D("200", "R")
        else:
            low, high, critical_low, critical_high = D("125", "R"), D("350", "R"), D("20", "R"), D("1000", "R")
        item["low"], item["high"] = low, high
        item["unit"] = {"GLU": "mmol/L", "HGB": "g/L", "PLT": "10^9/L"}[analyte]
        if item["value"] < critical_low or item["value"] > critical_high:
            item["flag"] = "CRITICAL"
        elif item["value"] < low or item["value"] > high:
            item["flag"] = "OUT_OF_RANGE"
        elif item["prev_value"] and item["hours"] is not None and item["hours"] <= 6:
            rate = abs(item["value"] - item["prev_value"]) / item["prev_value"]
            item["flag"] = "RATE_ALERT" if rate >= D("0.5", "R") else "NORMAL"
        else:
            item["flag"] = "NORMAL"
        item["metric"] = item["value"]
        item["limit"] = high
        out.append(item)
    for item in out:
        item.setdefault("label", str(item.get(SPEC["key"], "")))
    return out
