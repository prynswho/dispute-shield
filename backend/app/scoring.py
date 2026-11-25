"""Inference using trusted, fitted local artifacts."""

import json
from pathlib import Path
import sys

import joblib

from .connectors.files import artifact_dir
from .features import number, timestamp

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import early_win
import logistic_regression
import payment_risk


def artifact(name):
    path = artifact_dir() / name
    if not path.exists():
        raise RuntimeError(f"Required scoring artifact is unavailable: {name}")
    return joblib.load(path)


def payment_predictions(inputs):
    risk = artifact("payment_risk/model.joblib")
    early = artifact("early_win.joblib")
    tiers_path = artifact_dir() / "payment_risk" / "tiers.json"
    if not tiers_path.exists():
        raise RuntimeError("Payment-risk tier thresholds are unavailable")
    tiers = json.loads(tiers_path.read_text())
    probabilities = payment_risk.predict(risk, inputs)
    win_model = early["payment_win_prob"]
    wins = early_win.predict(win_model, inputs) if win_model else [None] * len(inputs)
    return zip(probabilities, wins, strict=True), tiers


def score_payments(payments, inputs, checklists):
    eligible = [row for row in inputs if row is not None]
    predictions, tiers = payment_predictions(eligible) if eligible else (iter(()), {})
    results = []
    for payment, feature_row, actions in zip(payments, inputs, checklists, strict=True):
        amount = number(payment["amount_usd"], "amount_usd", positive=True)
        risk_prob, win_prob = next(predictions) if feature_row is not None else (None, None)
        tier = None
        if risk_prob is not None:
            tier = "low"
            if risk_prob >= tiers["high_min_score"]:
                tier = "high"
            elif risk_prob >= tiers["medium_min_score"]:
                tier = "medium"
        if tier == "high":
            actions = ["Review the payment and preserve the service evidence promptly.", *actions]
        results.append({
            "payment_id": payment["payment_id"], "invoice_id": payment["invoice_id"],
            "team_id": payment["team_id"], "amount_usd": amount,
            "collected_at": payment["collected_at"],
            "invoice_win_prob": None, "payment_win_prob": win_prob,
            "dispute_risk_tier": tier, "dispute_risk_score": risk_prob,
            "expected_loss_usd": risk_prob * (1 - win_prob) * (amount + 25) if win_prob is not None else None,
            "actions": actions,
        })
    return results


def recommendation(win_prob, amount):
    return "fight" if win_prob * (amount + 25) > 15 else "accept"


def score_disputes(disputes, payments):
    by_payment = {row["payment_id"]: row for row in payments}
    for dispute in disputes:
        payment = by_payment.get(dispute["payment_id"])
        if payment is None:
            raise ValueError("Every dispute must reference a payment in this upload")
        if (dispute["team_id"] != payment["team_id"] or
                payment["invoice_id"] and dispute["invoice_id"] != payment["invoice_id"]):
            raise ValueError("Dispute invoice_id and team_id must match its payment")
        number(dispute["amount_usd"], "amount_usd", positive=True)
        opened = timestamp(dispute["opened_at"], "opened_at")
        if opened < timestamp(payment["collected_at"], "collected_at"):
            raise ValueError("A dispute cannot open before its payment was collected")
    probabilities = logistic_regression.predict(artifact("dispute_win.joblib"), disputes)
    return [{
        "dispute_id": row["dispute_id"], "payment_id": row["payment_id"], "team_id": row["team_id"],
        "reason": row["reason"], "amount_usd": float(row["amount_usd"]), "win_prob": probability,
        "recommendation": recommendation(probability, float(row["amount_usd"])), "outcome": None,
    } for row, probability in zip(disputes, probabilities, strict=True)]
