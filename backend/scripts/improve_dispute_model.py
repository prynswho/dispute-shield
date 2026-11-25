"""Evaluate tuned interactions and sigmoid calibration on the locked dispute folds."""

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from compare_dispute_models import LOGISTIC_V1, MINIMUM_GAIN, select_by_log_loss
from evaluate_disputes import calibration, expanding_folds, fold_metadata, load_rows, metrics, score_summary
import logistic_regression


INTERACTIONS = "v1_reason_evidence_interactions"
CALIBRATED_V1 = "v1_sigmoid_calibration"
REGULARIZATION_OPTIONS = (0.1, 0.3, 1.0)
INNER_TRAIN_FRACTION = 0.75
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "experiments" / "v1_improvements"


def inner_split(outer_train):
    cutoff = outer_train.iloc[int(INNER_TRAIN_FRACTION * len(outer_train))]["opened_at"]
    earlier = outer_train.loc[outer_train["opened_at"] < cutoff]
    train = earlier.loc[earlier["closed_at"] <= cutoff]
    validation = outer_train.loc[outer_train["opened_at"] >= cutoff]
    if train["outcome"].nunique() != 2 or validation["outcome"].nunique() != 2:
        raise ValueError("Inner training and validation each need both outcomes")
    return cutoff, len(earlier) - len(train), train, validation


def fit_interactions(rows, c):
    return logistic_regression.fit_classifier(rows, LogisticRegression(C=c), include_interactions=True)


def prediction_rows(frame):
    return frame.drop(columns=["outcome", "closed_at"]).to_dict("records")


def decision_scores(model, rows):
    return model["pipeline"].decision_function(logistic_regression.model_features(model, rows)).reshape(-1, 1)


def fit_candidates(outer_train):
    cutoff, excluded, inner_train, inner_validation = inner_split(outer_train)
    early_rows = inner_train.to_dict("records")
    validation_rows = prediction_rows(inner_validation)
    validation_outcomes = inner_validation["outcome"].eq("won").astype(int).to_numpy()
    inner_losses = {}
    for c in REGULARIZATION_OPTIONS:
        interaction_model = fit_interactions(early_rows, c)
        validation_predictions = logistic_regression.predict(interaction_model, validation_rows)
        inner_losses[c] = log_loss(validation_outcomes, validation_predictions, labels=[0, 1])
    chosen_c = min(inner_losses, key=inner_losses.get)

    inner_v1 = logistic_regression.fit(early_rows)
    calibrator = LogisticRegression(C=float("inf")).fit(
        decision_scores(inner_v1, validation_rows), validation_outcomes,
    )
    outer_rows = outer_train.to_dict("records")
    return {
        LOGISTIC_V1: logistic_regression.fit(outer_rows),
        INTERACTIONS: fit_interactions(outer_rows, chosen_c),
        CALIBRATED_V1: calibrator,
    }, {
        "cutoff": str(cutoff),
        "train_rows": len(inner_train),
        "validation_rows": len(inner_validation),
        "excluded_by_closure": excluded,
        "interaction_c_log_loss": inner_losses,
        "chosen_interaction_c": chosen_c,
    }


def predict_candidates(models, rows):
    v1 = models[LOGISTIC_V1]
    return {
        LOGISTIC_V1: logistic_regression.predict(v1, rows),
        INTERACTIONS: logistic_regression.predict(models[INTERACTIONS], rows),
        CALIBRATED_V1: models[CALIBRATED_V1].predict_proba(decision_scores(v1, rows))[:, 1],
    }


def grouped_errors(test, actual, probabilities):
    frame = test[["reason", "merchant_responded"]].reset_index(drop=True)
    for column in frame:
        frame[column] = frame[column].str.strip().str.lower()
    frame = frame.assign(actual=actual, predicted=probabilities)
    for dimension in ("reason", "merchant_responded"):
        for value, group in frame.groupby(dimension, sort=True):
            actual_win_rate = group["actual"].mean()
            mean_prediction = group["predicted"].mean()
            yield {
                "dimension": dimension,
                "value": value,
                "count": len(group),
                "actual_win_rate": actual_win_rate,
                "mean_prediction": mean_prediction,
                "prediction_minus_actual": mean_prediction - actual_win_rate,
                **metrics(group["actual"], group["predicted"]),
            }


def selection_decision(scores):
    selected, candidates = select_by_log_loss(scores, (CALIBRATED_V1, INTERACTIONS))
    return {
        "selected_model": selected,
        "logistic_v1_frozen": selected == LOGISTIC_V1,
        "minimum_log_loss_gain_each_fold": float(MINIMUM_GAIN),
        "tie_break": CALIBRATED_V1,
        "candidates": candidates,
    }


def evaluate_improvements(frame, output_dir):
    fold_reports = []
    scores = []
    calibration_tables = []
    diagnostics = []
    for number, cutoff, excluded, train, test in expanding_folds(frame):
        models, inner_report = fit_candidates(train)
        fold_reports.append({**fold_metadata(number, cutoff, excluded, train, test), "inner": inner_report})
        actual = test["outcome"].eq("won").astype(int).to_numpy()
        for model, probabilities in predict_candidates(models, prediction_rows(test)).items():
            scores.append({"fold": number, "model": model, **metrics(actual, probabilities)})
            calibration_tables.append(
                calibration(actual, probabilities).reset_index().assign(fold=number, model=model)
            )
            diagnostics.extend(
                {"fold": number, "model": model, **group}
                for group in grouped_errors(test, actual, probabilities)
            )

    scores = pd.DataFrame(scores)
    decision = selection_decision(scores)
    output_dir.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_dir / "scores.csv", index=False)
    score_summary(scores).to_csv(output_dir / "summary.csv")
    pd.concat(calibration_tables).to_csv(output_dir / "calibration.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(output_dir / "grouped_errors.csv", index=False)
    (output_dir / "folds.json").write_text(json.dumps(fold_reports, indent=2) + "\n")
    (output_dir / "selection.json").write_text(json.dumps(decision, indent=2) + "\n")
    print(scores.to_string(index=False))
    print(json.dumps(decision, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Local disputes.csv path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output_dir.exists() and (
        not args.output_dir.is_dir() or any(args.output_dir.iterdir())
    ):
        parser.error("Choose an empty output directory to preserve existing reports.")
    frame = load_rows(args.csv_path, extra_columns=("merchant_responded", "amount_usd"))
    evaluate_improvements(frame, args.output_dir)


if __name__ == "__main__":
    main()
