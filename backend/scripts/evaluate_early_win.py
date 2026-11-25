"""Evaluate win probabilities conditional on a payment being disputed."""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import early_win
from evaluate_disputes import calibration, expanding_folds, fold_metadata, load_rows, metrics, score_summary
from joined_features import PAYMENT_CATEGORIES, boolean_values, join_required, photo_counts, read_table


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "experiments" / "early_win"


def load_features(folder):
    disputes = load_rows(folder / "disputes.csv", ("payment_id", "invoice_id", "team_id"))
    payments = read_table(folder, "payments.csv", [
        "payment_id", "invoice_id", "team_id", "collected_at", "amount_usd",
        "receipt_sent", *PAYMENT_CATEGORIES,
    ], "payment_id").rename(columns={"amount_usd": "payment_amount"})
    invoices = read_table(folder, "invoices.csv", [
        "invoice_id", "team_id", "amount_usd", "job_type",
    ], "invoice_id").rename(columns={"amount_usd": "invoice_amount"})
    photos = read_table(folder, "photos.csv", ["photo_id", "invoice_id", "kind", "uploaded_at"], "photo_id")
    for frame, column in ((payments, "collected_at"), (photos, "uploaded_at")):
        frame[column] = pd.to_datetime(frame[column], format="mixed", utc=True, errors="coerce")
        if frame[column].isna().any():
            raise ValueError(f"Missing or invalid {column}")
    if not photos["kind"].isin(["before", "after"]).all():
        raise ValueError("Unexpected photo kind")

    # Match IDs from both sources so inconsistent keys cannot silently join.
    joined = join_required(disputes, payments, ["payment_id", "invoice_id", "team_id"])
    joined = join_required(joined, invoices, ["invoice_id", "team_id"])
    if not joined["dispute_id"].equals(disputes["dispute_id"]):
        raise ValueError("Joins changed dispute order or membership")
    if joined["collected_at"].gt(joined["opened_at"]).any():
        raise ValueError("A joined payment was collected after its dispute opened")
    unique_payments = joined.drop_duplicates("payment_id")
    joined = join_required(joined, photo_counts(unique_payments, photos), "payment_id")
    for column in ("invoice_amount", "payment_amount"):
        amounts = pd.to_numeric(joined[column], errors="coerce")
        if not (np.isfinite(amounts) & amounts.gt(0)).all():
            raise ValueError(f"{column} must contain positive finite amounts")
        joined[column] = amounts
    for column in (*PAYMENT_CATEGORIES, "job_type"):
        joined[column] = joined[column].str.strip().str.lower().replace("", "na")
    joined["card_country"] = joined["card_country"].where(
        joined["card_country"].isin(["us", "na"]), "foreign"
    )
    joined["receipt_sent"] = boolean_values(joined["receipt_sent"])
    return joined


def evaluate_stage(frame, stage, output):
    models = early_win.candidates(stage)
    frame = frame.assign(stage_amount=frame[f"{stage}_amount"])
    frame["log_amount"] = np.log(frame["stage_amount"])
    results, calibration_tables, folds = [], [], []
    for number, cutoff, excluded, train, test in expanding_folds(frame):
        folds.append(fold_metadata(number, cutoff, excluded, train, test))
        training = train.to_dict("records")
        scoring = test.drop(columns=["outcome", "closed_at"]).to_dict("records")
        actual = test["outcome"].eq("won").to_numpy(dtype=int)
        probabilities = {"constant": np.full(len(test), train["outcome"].eq("won").mean())}
        for name, (fit, predict) in models.items():
            probabilities[name] = predict(fit(training), scoring)
        for name, scores in probabilities.items():
            results.append({"fold": number, "model": name, **metrics(actual, scores)})
            calibration_tables.append(calibration(actual, scores).reset_index().assign(fold=number, model=name))

    results = pd.DataFrame(results)
    losses = results.pivot(index="fold", columns="model", values="log_loss")
    passes = [name for name in models if losses[name].lt(losses["constant"]).all()]
    # Invoice amount and job type are snapshot values. Payment lookup also uses job type.
    deployable = [name for name in passes if stage == "payment" and name != "lookup"]
    selected = min(deployable, key=lambda name: losses[name].mean(), default=None)
    model = None if selected is None else models[selected][0](frame.to_dict("records"))
    decision = {
        "stage": stage,
        "selection_rule": "Strictly lower log loss than the constant in both folds and verified feature timing.",
        "beat_constant_in_both_folds": passes,
        "snapshot_dependent_candidates": list(models) if stage == "invoice" else ["lookup"],
        "selected": selected,
        "blank_export": selected is None,
        "amount_band_edges_usd": early_win.AMOUNT_EDGES,
    }
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / "scores.csv", index=False)
    score_summary(results).to_csv(output / "summary.csv")
    pd.concat(calibration_tables, ignore_index=True).to_csv(output / "calibration.csv", index=False)
    (output / "folds.json").write_text(json.dumps(folds, indent=2) + "\n")
    (output / "selection.json").write_text(json.dumps(decision, indent=2) + "\n")
    print(f"\n{stage}_win_prob\n{results.to_string(index=False)}")
    print(json.dumps(decision, indent=2))
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--model-path", type=Path, default=ROOT / "artifacts" / "early_win.joblib")
    args = parser.parse_args()
    frame = load_features(args.data_dir)
    bundle = {
        f"{stage}_win_prob": evaluate_stage(frame, stage, args.output_dir / stage)
        for stage in ("invoice", "payment")
    }
    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.model_path)
