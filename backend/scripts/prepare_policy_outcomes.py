"""Score local unresolved disputes and save policy aggregates without row identities."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.policies import DATA_DIR, OUTCOMES, evaluate_policies
from app.policy_outcomes import build_sensitivity
from joined_features import boolean_values, read_table
import logistic_regression


ROOT = Path(__file__).resolve().parents[2]


def validate_aggregate_cohort(frame):
    address = json.loads((DATA_DIR / "address_mandatory.json").read_text())
    for group in address["groups"]:
        matching = frame["address_present"].eq(group["address"] == "present")
        matching &= frame["invoice_amount"].lt(300).eq(group["band"] == "under_300")
        sample = frame.loc[matching]
        if any(int(sample["outcome"].eq(outcome).sum()) != group[outcome] for outcome in OUTCOMES):
            raise ValueError("Local outcome counts differ from the supplied address aggregates")
        observed_loss = sample.loc[sample["outcome"].eq("lost"), "amount_usd"].add(25).sum()
        if not np.isclose(observed_loss, group["usd_lost"], rtol=0, atol=0.01):
            raise ValueError("Local lost dollars differ from the supplied address aggregates")
    signed = json.loads((DATA_DIR / "signed_estimate_over_1000.json").read_text())
    for group in signed["groups"]:
        for status in ("unsigned", "signed"):
            matching = frame["invoice_amount"].gt(1000) & frame["reason"].eq(group["reason"])
            matching &= frame["signed_estimate"].eq(status == "signed")
            sample = frame.loc[matching]
            if any(int(sample["outcome"].eq(outcome).sum()) != group[status][outcome] for outcome in OUTCOMES):
                raise ValueError("Local outcome counts differ from the supplied signed-estimate aggregates")


def prepare(data_dir, model_path, output_path):
    disputes = read_table(data_dir, "disputes.csv", [
        "dispute_id", "invoice_id", "team_id", "reason", "outcome",
        "amount_usd", "merchant_responded", "evidence_submitted",
    ], "dispute_id")
    invoices = read_table(data_dir, "invoices.csv", [
        "invoice_id", "team_id", "amount_usd", "customer_address_present", "signed_estimate",
    ], "invoice_id").rename(columns={
        "amount_usd": "invoice_amount", "customer_address_present": "address_present",
    })
    frame = disputes.merge(invoices, on=["invoice_id", "team_id"], how="left", validate="many_to_one", indicator=True)
    if not frame["_merge"].eq("both").all():
        raise ValueError("Every policy dispute must match an invoice and team")
    for column in ("outcome", "reason", "merchant_responded"):
        frame[column] = frame[column].str.strip().str.lower()
    if not frame["outcome"].isin(OUTCOMES).all():
        raise ValueError("Unexpected historical dispute outcome")
    for column in ("amount_usd", "invoice_amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if not (np.isfinite(frame[column]) & frame[column].gt(0)).all():
            raise ValueError("Policy amounts must be positive and finite")
    for column in ("address_present", "signed_estimate"):
        frame[column] = boolean_values(frame[column]).astype(bool)
    validate_aggregate_cohort(frame)
    pending = frame.loc[frame["outcome"].isin(["open", "withdrawn"])].copy()
    valid = pending["merchant_responded"].isin(["true", "false"]) & pending["reason"].ne("")
    unscorable = int((~valid).sum())
    print(f"Unresolved rows {len(pending)}, unscorable rows {unscorable}")
    if unscorable:
        raise ValueError("Some unresolved rows cannot be scored. No sensitivity artifact was written.")
    model = joblib.load(model_path)
    if model.get("groups") or not model.get("include_merchant_response", True) or model.get("include_interactions", False):
        raise ValueError("Use the frozen dispute-stage logistic v1 artifact")
    probabilities = logistic_regression.predict(model, pending.to_dict("records"))
    pending["win_prob"] = probabilities
    columns = ["outcome", "amount_usd", "invoice_amount", "address_present",
               "signed_estimate", "reason", "win_prob"]
    reports = evaluate_policies("resolved_only")
    aggregate = build_sensitivity(reports, pending[columns].to_dict("records"))
    aggregate["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    aggregate["source"] = "Frozen dispute logistic v1 scored local open and withdrawn cases. Only aggregate policy effects are retained."
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(aggregate, indent=2) + "\n")
    temporary.replace(output_path)
    print(json.dumps({"outcome_counts": aggregate["counts"], "policies": list(aggregate["policies"])}))
    return aggregate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--model-path", type=Path, default=ROOT / "artifacts/dispute_win.joblib")
    parser.add_argument("--output-path", type=Path, default=DATA_DIR / "outcome_sensitivity.json")
    args = parser.parse_args()
    prepare(args.data_dir, args.model_path, args.output_path)
