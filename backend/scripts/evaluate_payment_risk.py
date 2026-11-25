"""Compare payment dispute-risk models on chronological expanding folds."""

import argparse
from functools import partial
import hashlib
import json
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from evaluate_disputes import calibration, metrics, score_summary
import payment_risk
from payment_risk_features import INVOICE_FLAGS, LABEL, feature_columns, load_rows


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "experiments" / "payment_risk"
RISK_FOLD_EDGES = {
    "two_folds": (0.5, 0.75, 1.0),
    "three_folds": (0.4, 0.6, 0.8, 1.0),
}


def expanding_folds(frame, edges=RISK_FOLD_EDGES["two_folds"]):
    size = len(frame)
    for number, (start, end) in enumerate(zip(edges[:-1], edges[1:]), 1):
        cutoff = frame.iloc[int(start * size)]["collected_at"]
        end_time = frame.iloc[int(end * size)]["collected_at"] if end < 1 else None
        train = frame.loc[frame["collected_at"] < cutoff]
        test = frame.loc[frame["collected_at"] >= cutoff]
        if end_time is not None:
            test = test.loc[test["collected_at"] < end_time]
        if train.empty or test.empty:
            raise ValueError(f"Fold {number} has empty training or test rows after keeping collection-time ties together")
        yield number, cutoff, end_time, train, test


def comparison_models():
    predict = payment_risk.predict
    return {
        "lookup": (payment_risk.fit_lookup, payment_risk.predict_lookup),
        "logistic_with_flags": (payment_risk.fit_logistic, predict),
        "logistic_without_flags": (partial(payment_risk.fit_logistic, include_invoice_flags=False), predict),
        "hgb_with_flags": (payment_risk.fit_hgb, predict),
        "hgb_without_flags": (partial(payment_risk.fit_hgb, include_invoice_flags=False), predict),
    }


def fold_metadata(number, cutoff, end_time, train, test):
    sorted_ids = json.dumps(sorted(test["payment_id"]), ensure_ascii=False)
    return {
        "fold": number,
        "cutoff": cutoff.isoformat(),
        "test_end_exclusive": end_time.isoformat() if end_time is not None else None,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_disputed_rows": int(train[LABEL].sum()),
        "test_disputed_rows": int(test[LABEL].sum()),
        "train_dispute_rate": float(train[LABEL].mean()),
        "test_dispute_rate": float(test[LABEL].mean()),
        "sorted_test_ids_sha256": hashlib.sha256(sorted_ids.encode("utf-8")).hexdigest(),
    }


def invoice_flag_deltas(scores):
    deltas = []
    for family in ("logistic", "hgb"):
        with_flags = scores.loc[scores["model"].eq(f"{family}_with_flags")].set_index("fold")
        without_flags = scores.loc[scores["model"].eq(f"{family}_without_flags")].set_index("fold")
        columns = ["auc", "log_loss", "brier"]
        differences = with_flags[columns] - without_flags[columns]
        differences.loc["mean"] = differences.mean()
        deltas.append(differences.add_suffix("_delta").reset_index().assign(family=family))
    return pd.concat(deltas, ignore_index=True)


def capture_metrics(actual, probabilities):
    # Stable sorting breaks ties in test order (collected_at, then payment_id).
    ranked = actual[np.argsort(-np.asarray(probabilities), kind="stable")]
    total = int(actual.sum())
    result = {}
    for percent in (1, 2, 5):
        slots = ceil(len(actual) * percent / 100)
        captured = int(ranked[:slots].sum())
        result.update({
            f"top_{percent}pct_rows": slots,
            f"top_{percent}pct_disputes": captured,
            f"top_{percent}pct_capture_rate": captured / total if total else np.nan,
        })
    return result


def evaluate(frame, cohort, output_dir, *, layout="two_folds", focused=False):
    if frame.empty:
        raise ValueError("No eligible payments")
    folds = []
    score_rows = []
    calibration_tables = []
    models = comparison_models()
    if focused:
        models = {"logistic_without_flags": models["logistic_without_flags"]}
    edges = RISK_FOLD_EDGES[layout]
    print(f"Payment cohort {json.dumps(cohort, sort_keys=True)}")
    for number, cutoff, end_time, train, test in expanding_folds(frame, edges):
        if train[LABEL].nunique() != 2:
            raise ValueError(f"Fold {number} needs both classes in training for logistic regression")
        details = fold_metadata(number, cutoff, end_time, train, test)
        folds.append(details)
        print(f"\nFold {number} {json.dumps(details, sort_keys=True)}")
        train_rows = train.drop(columns=["payment_id", "collected_at"]).to_dict("records")
        test_rows = test.drop(columns=["payment_id", "collected_at", LABEL]).to_dict("records")
        actual = test[LABEL].to_numpy()
        predictions = {"constant": np.full(len(test), details["train_dispute_rate"])}
        for name, (fit, predict) in models.items():
            predictions[name] = predict(fit(train_rows), test_rows)
        fold_scores = {name: metrics(actual, probs) for name, probs in predictions.items()}
        constant_loss = fold_scores["constant"]["log_loss"]
        for name, probabilities in predictions.items():
            scores = fold_scores[name]
            if focused:
                scores["pr_auc_ap"] = average_precision_score(actual, probabilities) if actual.any() else np.nan
                scores["relative_log_loss_gain"] = (constant_loss - scores["log_loss"]) / constant_loss
                scores.update(capture_metrics(actual, probabilities))
            score_rows.append({"fold": number, "model": name, **scores})
            table = calibration(actual, probabilities).rename(columns={"actual_win_rate": "actual_dispute_rate"})
            calibration_tables.append(table.reset_index().assign(fold=number, model=name))
            print(f"\n{name} calibration\n{table.to_string(float_format=lambda value: f'{value:.4f}')}")

    scores = pd.DataFrame(score_rows)
    summary = score_summary(scores)
    print(f"\nPer-fold scores\n{scores.to_string(index=False)}")
    print(f"\nAcross-fold scores (population standard deviation)\n{summary.to_string()}")

    output_dir.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_dir / "scores.csv", index=False)
    summary.to_csv(output_dir / "summary.csv")
    pd.concat(calibration_tables, ignore_index=True).to_csv(output_dir / "calibration.csv", index=False)
    if not focused:
        deltas = invoice_flag_deltas(scores)
        print(f"\nInvoice flag effect (with minus without)\n{deltas.to_string(index=False)}")
        deltas.to_csv(output_dir / "invoice_flags_delta.csv", index=False)
    (output_dir / "folds.json").write_text(json.dumps(folds, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "cohort": cohort,
        "label": "Payment ID appears in the supplied disputes snapshot, regardless of dispute outcome.",
        "label_timing": "Labels use the full snapshot, so fold-time label availability and follow-up are unverified.",
        "invoice_timing": "Invoice flags, line_item_count, and job_type are supplied snapshot values.",
        "photo_timing": "Photos on the same invoice count when uploaded_at <= collected_at.",
        "layout": layout,
        "fold_edges": edges,
        "constant_features": [],
        "lookup_features": ["payment_method", "avs_result"],
        "learned_features_with_flags": feature_columns(),
        "learned_features_without_flags": feature_columns(include_invoice_flags=False),
        "removed_invoice_flags": INVOICE_FLAGS,
    }
    if focused:
        metadata.update({
            "pr_auc_definition": "Average precision (AP).",
            "relative_log_loss_gain": "(constant log loss - model log loss) / constant log loss.",
            "top_capture": "Round each budget up to whole payments. Break score ties by collection time then payment ID.",
        })
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"\nReports written to {output_dir}")
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="Directory containing payments, invoices, photos, and disputes CSVs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Directory for aggregate reports")
    parser.add_argument("--compare-layouts", action="store_true",
                        help="Evaluate constant and flag-free logistic in separate two- and three-fold reports")
    args = parser.parse_args()
    frame, cohort = load_rows(args.data_dir)
    if args.compare_layouts:
        for layout in RISK_FOLD_EDGES:
            print(f"\nPayment risk layout: {layout}")
            evaluate(frame, cohort, args.output_dir / layout, layout=layout, focused=True)
    else:
        evaluate(frame, cohort, args.output_dir)


if __name__ == "__main__":
    main()
