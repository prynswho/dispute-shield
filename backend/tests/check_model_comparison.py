"""Run with PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_model_comparison.py."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from compare_dispute_models import (
    ABLATION, BOOSTING_JOINED, BOOSTING_V1, LOGISTIC_V1, comparison_models, selection_decision,
)
from evaluate_disputes import expanding_folds, fold_metadata, load_joined_rows
from joined_features import INVOICE_FLAGS, INVOICE_NUMERIC, PAYMENT_CATEGORIES


def check_selection():
    def select(v1, small, full):
        losses = {LOGISTIC_V1: v1, BOOSTING_V1: small, BOOSTING_JOINED: full,
                  ABLATION: (0.01, 0.01), "v1+A+B+C+D": (0.02, 0.02)}
        scores = pd.DataFrame([
            {"fold": fold, "model": model, "log_loss": loss}
            for model, values in losses.items()
            for fold, loss in enumerate(values, 1)
        ])
        return selection_decision(scores)

    tied = select((0.06, 0.45), (0.05, 0.44), (0.049, 0.441))
    assert tied["selected_model"] == BOOSTING_V1
    assert tied["boosting_candidates"][BOOSTING_V1]["log_loss_gain_by_fold"] == {1: 0.01, 2: 0.01}
    equal_eligible_means = select((0.50, 0.50), (0.40, 0.44), (0.44, 0.40))
    assert equal_eligible_means["selected_model"] == BOOSTING_V1
    assert all(item["eligible"] for item in equal_eligible_means["boosting_candidates"].values())
    assert select((0.50, 0.50), (0.44, 0.44), (0.42, 0.43))["selected_model"] == BOOSTING_JOINED
    failed = select((0.50, 0.50), (0.20, 0.49001), (0.49, 0.50))
    assert not any(item["eligible"] for item in failed["boosting_candidates"].values())
    assert failed["selected_model"] == LOGISTIC_V1
    assert failed["explanation_only_models"] == [ABLATION]


def check_folds():
    opened = pd.Timestamp("2025-01-01", tz="UTC") + pd.to_timedelta(
        [0, 1, 2, 3, 4, 5, 6, 7, 7, 8, 10, 11, 11, 12, 13, 14], unit="D"
    )
    closed = pd.Series(opened)
    closed.iloc[0] = opened[8]
    closed.iloc[1] = opened[9]
    frame = pd.DataFrame({"dispute_id": [f"d{i}" for i in range(16)],
                          "opened_at": opened, "closed_at": closed})
    first, second = expanding_folds(frame)
    assert (first[1], first[2], first[3].index.tolist(), first[4].index.tolist()) == (
        opened[8], 1, [0, 2, 3, 4, 5, 6], [7, 8, 9, 10],
    )
    assert (second[1], second[2], second[3].index.tolist(), second[4].index.tolist()) == (
        opened[12], 0, list(range(11)), list(range(11, 16)),
    )
    metadata = fold_metadata(*first)
    test_ids = json.dumps(["d10", "d7", "d8", "d9"]).encode("utf-8")
    assert metadata["sorted_test_ids_sha256"] == hashlib.sha256(test_ids).hexdigest()
    assert metadata == fold_metadata(*first[:3], first[3].iloc[::-1], first[4].iloc[::-1])
    assert {key for key in metadata if key.endswith("sha256")} == {"sorted_test_ids_sha256"}


def write_synthetic_inputs(folder):
    tables = {name: [] for name in ("disputes", "payments", "invoices", "photos", "teams")}
    for team in range(3):
        tables["teams"].append({"team_id": f"t{team}", "profession": "repair", "team_size": team + 2})
    for index, opened_at in enumerate(pd.date_range("2025-01-01", periods=96, tz="UTC")):
        payment, invoice, team = f"p{index}", f"i{index}", f"t{index % 3}"
        tables["disputes"].append({
            "dispute_id": f"d{index}", "payment_id": payment, "invoice_id": invoice, "team_id": team,
            "opened_at": opened_at, "closed_at": opened_at + pd.Timedelta(days=1),
            "outcome": "won" if index % 2 else "lost", "reason": "test_only" if index >= 48 else "known",
            "evidence_submitted": "late_token" if index >= 48 else "receipt",
            "merchant_responded": "true" if index % 2 else "false", "amount_usd": 20 + index,
        })
        tables["payments"].append({
            "payment_id": payment, "invoice_id": invoice, "team_id": team,
            "collected_at": opened_at, "receipt_sent": "true",
            **dict.fromkeys(PAYMENT_CATEGORIES, "na"),
        })
        tables["invoices"].append({
            "invoice_id": invoice, "team_id": team, "created_at": opened_at - pd.Timedelta(days=1),
            "job_type": "repair", **dict.fromkeys(INVOICE_FLAGS, "true"),
            **dict.fromkeys(INVOICE_NUMERIC, 3),
        })
        tables["photos"].append({
            "photo_id": f"photo{index}", "invoice_id": invoice, "kind": "before", "uploaded_at": opened_at,
        })
    for name, table in tables.items():
        pd.DataFrame(table).to_csv(folder / f"{name}.csv", index=False)


def check_pipelines(frame):
    _, _, _, train, test = next(expanding_folds(frame))
    train_rows = train.to_dict("records")
    test_rows = test.drop(columns=["outcome", "closed_at"]).to_dict("records")
    models = comparison_models()
    feature_counts = {}
    for name in (BOOSTING_V1, BOOSTING_JOINED):
        fit, predict = models[name]
        model = fit(train_rows)
        pipeline = model["pipeline"]
        settings = pipeline["classifier"].get_params()
        assert {key: settings[key] for key in
                ("max_depth", "learning_rate", "max_iter", "early_stopping", "random_state")} == {
                    "max_depth": 3, "learning_rate": 0.05, "max_iter": 200,
                    "early_stopping": False, "random_state": 42,
                }
        features = pipeline["features"]
        assert not features.sparse_output_
        names = features.get_feature_names_out()
        assert "reason__reason_known" in names
        assert not any("test_only" in field or "late_token" in field for field in names)
        feature_counts[name] = len(names)
        probabilities = predict(model, test_rows)
        assert len(probabilities) == len(test_rows)
        assert np.isfinite(probabilities).all()
        assert all(0 <= probability <= 1 for probability in probabilities)
    assert feature_counts[BOOSTING_V1] < feature_counts[BOOSTING_JOINED]

    fit, predict = models[ABLATION]
    def no_response(rows):
        return [
            {key: value for key, value in row.items() if key != "merchant_responded"} for row in rows
        ]

    model = fit(no_response(train_rows))
    assert model["pipeline"]["classifier"].C == 1.0
    assert not any("merchant_responded" in name
                   for name in model["pipeline"]["features"].get_feature_names_out())
    assert predict(model, test_rows) == predict(model, no_response(test_rows))
    assert models[LOGISTIC_V1][0](train_rows)["pipeline"]["classifier"].C == 1.0


def check_report(input_csv, output_dir):
    script = Path(__file__).resolve().parents[1] / "scripts" / "compare_dispute_models.py"
    command = [sys.executable, str(script), str(input_csv), "--output-dir", str(output_dir)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    assert {item.name for item in output_dir.iterdir()} == {
        "scores.csv", "summary.csv", "calibration.csv", "folds.json", "selection.json",
    }
    scores = pd.read_csv(output_dir / "scores.csv")
    assert scores.groupby("fold").size().tolist() == [10, 10]
    summary = pd.read_csv(output_dir / "summary.csv", header=[0, 1], index_col=0)
    assert {"mean", "std", "min", "max", "defined_folds"} <= set(summary["log_loss"].columns)
    assert (summary["log_loss"]["defined_folds"] == 2).all()
    calibration = pd.read_csv(output_dir / "calibration.csv")
    assert len(calibration) == len(scores) * 10
    folds = json.loads((output_dir / "folds.json").read_text())
    for fold in folds:
        assert {key for key in fold if key.endswith("sha256")} == {"sorted_test_ids_sha256"}
        assert fold["test_rows"] == 24
    selection = json.loads((output_dir / "selection.json").read_text())
    assert selection["selected_model"] == selection_decision(scores)["selected_model"]
    retry = subprocess.run(command, check=False, capture_output=True, text=True)
    assert retry.returncode == 2 and "preserve existing reports" in retry.stderr


if __name__ == "__main__":
    check_selection()
    check_folds()
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        write_synthetic_inputs(folder)
        input_csv = folder / "disputes.csv"
        check_pipelines(load_joined_rows(input_csv))
        check_report(input_csv, folder / "reports")
    print("Selection, fold cutoffs, train-only pipelines, and aggregate report checks passed")
