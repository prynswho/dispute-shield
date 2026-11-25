"""Run with PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_v1_improvements.py."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

import improve_dispute_model as runner
import logistic_regression


def synthetic_rows():
    opened = pd.Series(pd.date_range("2025-01-01", periods=100, tz="UTC"))
    opened.iloc[59] = opened.iloc[60]
    closed = opened + pd.Timedelta(days=1)
    closed.iloc[56] = opened.iloc[60]
    closed.iloc[57] = opened.iloc[62]
    return pd.DataFrame({
        "dispute_id": [f"d{index}" for index in range(len(opened))],
        "opened_at": opened, "closed_at": closed,
        "outcome": ["won" if index % 3 else "lost" for index in range(len(opened))],
        "reason": ["review_only" if index >= 80 else "fraud" for index in range(len(opened))],
        "evidence_submitted": [
            "outer_only" if index >= 80 else "inner_validation_only" if index >= 59 else "receipt"
            for index in range(len(opened))
        ],
        "merchant_responded": ["true" if index % 2 else "false" for index in range(len(opened))],
        "amount_usd": [50 + index for index in range(len(opened))],
    })


def check_inner_cutoff_and_fitting(frame):
    outer_train = frame.iloc[:80]
    cutoff, excluded, train, validation = runner.inner_split(outer_train)
    assert cutoff == frame["opened_at"].iloc[60]
    assert excluded == 1 and len(train) == 58 and len(validation) == 21
    assert 56 in train.index and 57 not in train.index
    assert list(validation.index[:2]) == [59, 60]
    assert set(train.index).isdisjoint(validation.index)

    interactions = runner.fit_interactions(train.to_dict("records"), c=0.3)
    pipeline = interactions["pipeline"]
    names = pipeline["features"].get_feature_names_out()
    assert any("interactions__" in name and "fraud" in name and "receipt" in name for name in names)
    assert all("inner_validation_only" not in name for name in names)

    with patch.object(runner, "decision_scores", wraps=runner.decision_scores) as scoring:
        models, info = runner.fit_candidates(outer_train)
    scoring.assert_called_once()
    base, calibration_rows = scoring.call_args.args
    assert [row["dispute_id"] for row in calibration_rows] == validation["dispute_id"].tolist()
    assert all("outcome" not in row and "closed_at" not in row for row in calibration_rows)
    fitting_names = base["pipeline"]["features"].get_feature_names_out()
    assert all("inner_validation_only" not in name for name in fitting_names)
    assert len(info["interaction_c_log_loss"]) == 3
    assert info["chosen_interaction_c"] == min(
        info["interaction_c_log_loss"], key=info["interaction_c_log_loss"].get
    )

    fitted_names = models[runner.INTERACTIONS]["pipeline"]["features"].get_feature_names_out()
    assert any("inner_validation_only" in name for name in fitted_names)
    assert all("outer_only" not in name for name in fitted_names)
    test_rows = runner.prediction_rows(frame.iloc[80:])
    predictions = runner.predict_candidates(models, test_rows)
    assert all(len(values) == len(test_rows) and np.isfinite(values).all() for values in predictions.values())
    reference = logistic_regression.fit(outer_train.to_dict("records"))
    assert predictions[runner.LOGISTIC_V1] == logistic_regression.predict(reference, test_rows)


def check_selection():
    scores = pd.DataFrame([
        {"model": model, "fold": fold, "log_loss": loss}
        for model, losses in {
            runner.LOGISTIC_V1: (0.50, 0.50),
            runner.INTERACTIONS: (0.45, 0.495),
            runner.CALIBRATED_V1: (0.50, 0.50),
        }.items()
        for fold, loss in enumerate(losses, 1)
    ])
    decision = runner.selection_decision(scores)
    assert decision["logistic_v1_frozen"]
    assert decision["selected_model"] == runner.LOGISTIC_V1
    scores.loc[scores["model"].eq(runner.INTERACTIONS), "log_loss"] = 0.49
    decision = runner.selection_decision(scores)
    assert not decision["logistic_v1_frozen"]
    assert decision["selected_model"] == runner.INTERACTIONS


def check_report(frame, output_dir):
    runner.evaluate_improvements(frame, output_dir)
    scores = pd.read_csv(output_dir / "scores.csv")
    assert scores.groupby("fold").size().tolist() == [3, 3]
    folds = json.loads((output_dir / "folds.json").read_text())
    assert all(set(item["inner"]["interaction_c_log_loss"]) == {"0.1", "0.3", "1.0"} for item in folds)
    diagnostics = pd.read_csv(output_dir / "grouped_errors.csv")
    assert set(diagnostics["dimension"]) == {"reason", "merchant_responded"}
    for (_, _, _), group in diagnostics.groupby(["fold", "model", "dimension"]):
        assert group["count"].sum() == 25
    assert len(pd.read_csv(output_dir / "calibration.csv")) == 60


if __name__ == "__main__":
    rows = synthetic_rows()
    check_inner_cutoff_and_fitting(rows)
    check_selection()
    with TemporaryDirectory() as directory:
        check_report(rows, Path(directory))
    print("Inner split, tuning, calibration, v1 freeze, and aggregate diagnostics checks passed")
