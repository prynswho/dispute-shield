"""Fit and predict payment dispute-risk models with lists of row dicts."""

from collections import Counter

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from deterministic_baseline import MIN_N
from payment_risk_features import LABEL, feature_columns


def fit_lookup(rows):
    if not rows:
        raise ValueError("Cannot fit on empty payment rows")
    totals = Counter()
    disputes = Counter()
    for row in rows:
        method = row["payment_method"]
        for key in ((method, row["avs_result"]), (method,), ()):
            totals[key] += 1
            disputes[key] += row[LABEL]
    return {"totals": totals, "disputes": disputes}


def predict_lookup(model, rows):
    probabilities = []
    for row in rows:
        method = row["payment_method"]
        key = (method, row["avs_result"])
        if model["totals"][key] < MIN_N:
            key = (method,)
        if model["totals"][key] < MIN_N:
            key = ()
        probabilities.append((model["disputes"][key] + 1) / (model["totals"][key] + 2))
    return probabilities


def _model_frame(rows, columns):
    order = [name for group in columns.values() for name in group]
    return pd.DataFrame([{name: row[name] for name in order} for row in rows], columns=order)


def _fit(rows, classifier, include_invoice_flags, *, scale_numeric):
    columns = feature_columns(include_invoice_flags)
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    pipeline = Pipeline([
        ("features", ColumnTransformer([
            ("categorical", encoder, list(columns["categorical"])),
            ("numeric", StandardScaler() if scale_numeric else "passthrough", list(columns["numeric"])),
            ("binary", "passthrough", list(columns["binary"])),
        ])),
        ("classifier", classifier),
    ])
    pipeline.fit(_model_frame(rows, columns), [row[LABEL] for row in rows])
    return {"pipeline": pipeline, "columns": columns}


def fit_logistic(rows, *, include_invoice_flags=True):
    return _fit(rows, LogisticRegression(C=1.0), include_invoice_flags, scale_numeric=True)


def fit_hgb(rows, *, include_invoice_flags=True):
    classifier = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=200, early_stopping=False, random_state=42,
    )
    return _fit(rows, classifier, include_invoice_flags, scale_numeric=False)


def predict(model, rows):
    if not rows:
        return []
    return model["pipeline"].predict_proba(_model_frame(rows, model["columns"]))[:, 1].tolist()
