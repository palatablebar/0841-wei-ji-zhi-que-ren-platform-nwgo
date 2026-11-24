from app.domain.helpers import D


def decide_rows(items):
    for item in items:
        if item["flag"] == "CRITICAL":
            item["verdict"] = "REJECT"
            item["reason"] = "CRITICAL_VALUE"
        elif item["flag"] == "OUT_OF_RANGE":
            item["verdict"] = "REVIEW"
            item["reason"] = "OUT_OF_RANGE"
        elif item["flag"] == "RATE_ALERT":
            item["verdict"] = "REVIEW"
            item["reason"] = "RATE_ALERT"
        else:
            item["verdict"] = "PASS"
            item["reason"] = "IN_RANGE"
        item.setdefault("verdict", "PASS")
        item.setdefault("reason", "OK")
    return items
