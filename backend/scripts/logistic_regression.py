"""Estimate dispute win probability from the submitted case."""

import json
import math

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from deterministic_baseline import evidence_tokens


GROUPS = {
    "A": {
        "categorical": ["payment_method", "avs_result", "cvv_result", "card_country", "card_type"],
        "numeric": [],
        "binary": ["receipt_sent"],
    },
    "B": {
        "categorical": ["job_type"],
        "numeric": ["line_item_count", "job_description_chars"],
        "binary": ["customer_address_present", "signed_estimate", "terms_accepted",
                   "tech_gps_checkin", "completion_signature"],
    },
    "C": {
        "categorical": [],
        "numeric": ["photos_before_at_payment", "photos_after_at_payment"],
        "binary": ["team_used_completion_signature"],
    },
    "D": {"categorical": ["profession"], "numeric": ["team_size"], "binary": []},
}


def feature_columns(groups, include_merchant_response=True):
    columns = {"categorical": ["reason"], "numeric": ["n_evidence", "log_amount_usd"],
               "binary": ["merchant_responded"] if include_merchant_response else []}
    for group in groups:
        for kind, names in GROUPS[group].items():
            columns[kind].extend(names)
    assert not {"invoice_status", "updated_at"}.intersection(
        name for names in columns.values() for name in names
    ), "Forbidden invoice feature"
    return columns


def features(rows, groups=(), include_merchant_response=True, include_interactions=False):
    records = []
    for row in rows:
        tokens = evidence_tokens(row["evidence_submitted"])
        tokens.discard("none")
        amount = float(row["amount_usd"])
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("amount_usd must be positive and finite")
        record = {
            "reason": row["reason"].strip().lower(),
            "n_evidence": min(len(tokens), 6),
            "evidence": dict.fromkeys(tokens, 1),
            "log_amount_usd": math.log(amount),
        }
        if include_merchant_response:
            responded = str(row["merchant_responded"]).strip().lower()
            if responded not in {"true", "false"}:
                raise ValueError("merchant_responded must be true or false")
            record["merchant_responded"] = int(responded == "true")
        if include_interactions:
            record["reason_evidence"] = {
                json.dumps([record["reason"], token], ensure_ascii=False): 1 for token in tokens
            }
        records.append(record)
    frame = pd.DataFrame.from_records(records)
    columns = feature_columns(groups, include_merchant_response)
    for column in columns["categorical"][1:]:
        frame[column] = [str(row[column]).strip().lower() or "na" for row in rows]
    joined_binary = [column for group in groups for column in GROUPS[group]["binary"]]
    for column in columns["numeric"][2:] + joined_binary:
        values = pd.to_numeric(pd.Series([row[column] for row in rows]), errors="raise")
        if not values.map(math.isfinite).all():
            raise ValueError(f"Nonfinite or missing {column}")
        frame[column] = values
    return frame


def fit_classifier(
    rows, classifier, groups=(), include_merchant_response=True, scale_numeric=True,
    include_interactions=False,
):
    columns = feature_columns(groups, include_merchant_response)
    transforms = [
        ("reason", OneHotEncoder(handle_unknown="ignore", sparse_output=False), columns["categorical"]),
        ("numeric", StandardScaler() if scale_numeric else "passthrough", columns["numeric"]),
        ("evidence", DictVectorizer(sparse=False), "evidence"),
        ("response", "passthrough", columns["binary"]),
    ]
    if include_interactions:
        transforms.append(("interactions", DictVectorizer(sparse=False), "reason_evidence"))
    pipeline = Pipeline([
        ("features", ColumnTransformer(transforms)),
        ("classifier", classifier),
    ])
    labels = [int(row["outcome"] == "won") for row in rows]
    pipeline.fit(features(rows, groups, include_merchant_response, include_interactions), labels)
    return {"pipeline": pipeline, "groups": tuple(groups),
            "include_merchant_response": include_merchant_response,
            "include_interactions": include_interactions}


def fit(rows, groups=(), include_merchant_response=True):
    return fit_classifier(rows, LogisticRegression(C=1.0), groups, include_merchant_response)


def model_features(model, rows):
    return features(
        rows, model.get("groups", ()), model.get("include_merchant_response", True),
        model.get("include_interactions", False),
    )


def predict(model, rows):
    if not rows:
        return []
    return model["pipeline"].predict_proba(model_features(model, rows))[:, 1].tolist()


def top_coefficients(model):
    pipeline = model["pipeline"]
    names = pipeline["features"].get_feature_names_out()
    coefficients = pipeline["classifier"].coef_[0]
    return sorted(zip(names, coefficients), key=lambda item: -abs(item[1]))[:10]
