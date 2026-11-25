"""Dispute win-probability lookup baseline using training rows only."""

MIN_N = 20


def evidence_tokens(value):
    tokens = {token.strip().lower() for token in value.split(";")}
    tokens.discard("")
    if tokens == {"none"}:
        return set()
    return tokens


def evidence_count(value):
    return min(len(evidence_tokens(value)), 6)


def fit(rows):
    model = {"groups": {}, "reasons": {}, "overall": {"wins": 0, "total": 0}}
    for row in rows:
        if row["outcome"] not in {"won", "lost"}:
            raise ValueError("Training outcomes must be won or lost")
        reason = row["reason"].strip().lower()
        key = (reason, evidence_count(row["evidence_submitted"]))
        group = model["groups"].setdefault(key, {"wins": 0, "total": 0})
        reason_stats = model["reasons"].setdefault(reason, {"wins": 0, "total": 0})
        for stats in (group, reason_stats, model["overall"]):
            stats["total"] += 1
            stats["wins"] += int(row["outcome"] == "won")
    if model["overall"]["total"] == 0:
        raise ValueError("Cannot fit on empty training rows")
    return model


def predict_details(model, rows):
    predictions = []
    for row in rows:
        reason = row["reason"].strip().lower()
        key = (reason, evidence_count(row["evidence_submitted"]))
        stats = model["groups"].get(key)
        level = "reason_evidence"
        if stats is None or stats["total"] < MIN_N:
            stats = model["reasons"].get(reason)
            level = "reason"
        if stats is None or stats["total"] < MIN_N:
            stats = model["overall"]
            level = "overall"
        predictions.append({
            "win_prob": (stats["wins"] + 1) / (stats["total"] + 2),
            "level": level,
        })
    return predictions


def predict(model, rows):
    return [result["win_prob"] for result in predict_details(model, rows)]
