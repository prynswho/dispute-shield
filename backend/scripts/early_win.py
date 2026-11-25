"""Win-probability estimators for invoice and payment scoring."""

from bisect import bisect_right
from collections import Counter
from functools import partial

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from deterministic_baseline import MIN_N
from joined_features import PAYMENT_CATEGORIES


AMOUNT_EDGES = (100, 300, 1000)
PAYMENT_NUMERIC = ("log_amount", "photos_before_at_payment", "photos_after_at_payment")


def lookup_key(row):
    return bisect_right(AMOUNT_EDGES, row["stage_amount"]), row["job_type"]


def fit_lookup(rows):
    total, wins = Counter(), Counter()
    for row in rows:
        key = lookup_key(row)
        for group in (key, key[:1], ()):
            total[group] += 1
            wins[group] += row["outcome"] == "won"
    if not total:
        raise ValueError("Lookup requires training rows")
    return {"total": total, "wins": wins}


def predict_lookup(model, rows):
    total, wins = model["total"], model["wins"]
    probabilities = []
    for row in rows:
        key = lookup_key(row)
        group = next((group for group in (key, key[:1]) if total[group] >= MIN_N), ())
        probabilities.append((wins[group] + 1) / (total[group] + 2))
    return probabilities


def fit(rows, *, stage, boosting=False):
    if stage == "invoice":
        categories, numeric, binary = ["job_type"], ["log_amount"], []
    else:
        categories, numeric, binary = PAYMENT_CATEGORIES, list(PAYMENT_NUMERIC), ["receipt_sent"]
    columns = categories + numeric + binary
    processor = ColumnTransformer([
        ("category", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categories),
        ("numeric", "passthrough" if boosting else StandardScaler(), numeric),
        ("binary", "passthrough", binary),
    ])
    classifier = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=200, early_stopping=False, random_state=42,
    ) if boosting else LogisticRegression(C=1.0)
    pipeline = Pipeline([("features", processor), ("classifier", classifier)])
    pipeline.fit(pd.DataFrame.from_records(rows, columns=columns),
                 [row["outcome"] == "won" for row in rows])
    return {"pipeline": pipeline, "columns": columns}


def predict(model, rows):
    if not rows:
        return []
    features = pd.DataFrame.from_records(rows, columns=model["columns"])
    return model["pipeline"].predict_proba(features)[:, 1].tolist()


def candidates(stage):
    return {
        "lookup": (fit_lookup, predict_lookup),
        "logistic": (partial(fit, stage=stage), predict),
        "boosting": (partial(fit, stage=stage, boosting=True), predict),
    }
