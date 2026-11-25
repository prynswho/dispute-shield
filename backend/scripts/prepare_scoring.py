"""Prepare the frozen dispute model and historical dashboard totals."""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import logistic_regression
from evaluate_disputes import load_rows
from joined_features import read_table


DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "artifacts"
INVOICE_GAPS = {
    "customer_address_present": "Missing service address",
    "signed_estimate": "Missing signed estimate",
    "completion_signature": "Missing completion signature",
}
OUTCOMES = ("won", "lost", "open", "withdrawn")


def dispute_totals(disputes, key):
    groups = disputes.groupby(key, sort=True)
    totals = groups.size().rename("disputes").to_frame()
    for outcome in OUTCOMES:
        totals[outcome] = groups["outcome"].apply(lambda values: values.eq(outcome).sum())
    return totals.join(groups["usd_lost"].sum())


def historical_summary(folder):
    payments = read_table(folder, "payments.csv", ["payment_id", "team_id"], "payment_id")
    invoices = read_table(folder, "invoices.csv", ["invoice_id", "team_id", *INVOICE_GAPS], "invoice_id")
    disputes = read_table(folder, "disputes.csv",
                          ["dispute_id", "team_id", "reason", "outcome", "amount_usd"], "dispute_id")
    for column in ("outcome", "reason"):
        disputes[column] = disputes[column].str.strip().str.lower()
    if not disputes["outcome"].isin(OUTCOMES).all():
        raise ValueError("Historical dispute outcomes must be won, lost, open, or withdrawn")
    amount = pd.to_numeric(disputes["amount_usd"], errors="coerce")
    if not (np.isfinite(amount) & amount.gt(0)).all():
        raise ValueError("Historical dispute amounts must be positive and finite")
    disputes["usd_lost"] = (amount + 25).where(disputes["outcome"].eq("lost"), 0)

    reasons = []
    for reason, row in dispute_totals(disputes, "reason").iterrows():
        resolved = row["won"] + row["lost"]
        reasons.append({
            "reason": reason, "disputes": int(row["disputes"]),
            "wins": int(row["won"]), "losses": int(row["lost"]),
            "open": int(row["open"]), "withdrawn": int(row["withdrawn"]),
            "win_rate": float(row["won"] / resolved) if resolved else None,
            "usd_lost": round(float(row["usd_lost"]), 2),
        })

    team_totals = dispute_totals(disputes, "team_id").join(
        payments.groupby("team_id").size().rename("payments"), how="outer",
    )
    for field in INVOICE_GAPS:
        missing = invoices[field].str.strip().str.lower().eq("false")
        team_totals = team_totals.join(missing.groupby(invoices["team_id"]).sum().rename(field), how="outer")
    teams = []
    for team_id, row in team_totals.fillna(0).sort_index().iterrows():
        teams.append({
            "team_id": team_id, "payments": int(row["payments"]), "disputes": int(row["disputes"]),
            "wins": int(row["won"]), "losses": int(row["lost"]),
            "open": int(row["open"]), "withdrawn": int(row["withdrawn"]),
            "usd_lost": round(float(row["usd_lost"]), 2),
            "gaps": [
                {"label": label, "count": int(row[field])}
                for field, label in INVOICE_GAPS.items() if row[field] > 0
            ],
        })
    return {"reasons": reasons, "teams": teams}


def prepare(data_dir, output_dir):
    summary = historical_summary(data_dir)
    training = load_rows(data_dir / "disputes.csv", ("merchant_responded", "amount_usd"))
    model = logistic_regression.fit(training.to_dict("records"))
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_dir / "dispute_win.joblib")
    (output_dir / "historical_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Saved dispute logistic v1 fitted on {len(training):,} resolved disputes")
    print(f"Saved historical aggregates for {len(summary['teams'])} teams and {len(summary['reasons'])} reasons")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="Training data directory for months 1–22")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    prepare(args.data_dir, args.output_dir)
