"""Evaluate dispute models on two expanding folds; print aggregate results."""

import argparse
from collections import Counter
from pathlib import Path
from functools import partial
import json
import hashlib

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

import deterministic_baseline as baseline
import logistic_regression


def load_rows(path, extra_columns=()):
    columns = [
        "dispute_id", "opened_at", "closed_at", "outcome",
        "reason", "evidence_submitted", *extra_columns,
    ]
    frame = pd.read_csv(path, usecols=columns, dtype=str, keep_default_na=False)
    if frame["dispute_id"].eq("").any() or frame["dispute_id"].duplicated().any():
        raise ValueError("Dispute IDs must be present and unique")
    frame["outcome"] = frame["outcome"].str.strip().str.lower()
    frame = frame.loc[frame["outcome"].isin(["won", "lost"])].copy()
    for column in ["opened_at", "closed_at"]:
        frame[column] = pd.to_datetime(
            frame[column], format="mixed", errors="coerce", utc=True
        )
        if frame[column].isna().any():
            raise ValueError(f"Missing or invalid {column} among won/lost rows")
    if frame["closed_at"].lt(frame["opened_at"]).any():
        raise ValueError("Some disputes closed before they opened")
    return frame.sort_values(["opened_at", "dispute_id"]).reset_index(drop=True)


# Keep these boundaries fixed for comparisons across dispute models.
FOLD_EDGES = (0.5, 0.75, 1.0)


def expanding_folds(frame):
    n = len(frame)
    for number, (start, end) in enumerate(zip(FOLD_EDGES[:-1], FOLD_EDGES[1:]), 1):
        cutoff = frame.iloc[int(start * n)]["opened_at"]
        end_time = frame.iloc[int(end * n)]["opened_at"] if end < 1 else None
        candidates = frame.loc[frame["opened_at"] < cutoff]
        train = candidates.loc[candidates["closed_at"] <= cutoff]
        test = frame.loc[frame["opened_at"] >= cutoff]
        if end_time is not None:
            test = test.loc[test["opened_at"] < end_time]
        if train.empty or test.empty:
            raise ValueError(f"Fold {number} has empty eligible training or test rows")
        yield number, cutoff, len(candidates) - len(train), train, test


def load_joined_rows(path):
    from joined_features import enrich

    columns = ("merchant_responded", "amount_usd")
    original = load_rows(path, extra_columns=columns)
    frame = load_rows(path, extra_columns=(*columns, "payment_id", "invoice_id", "team_id"))
    frame = enrich(frame, Path(path).parent)
    for old_fold, new_fold in zip(expanding_folds(original), expanding_folds(frame), strict=True):
        for old_rows, new_rows in zip(old_fold[3:], new_fold[3:], strict=True):
            if old_rows["dispute_id"].tolist() != new_rows["dispute_id"].tolist():
                raise ValueError("Joining changed the train or test dispute IDs")
    return frame


def cumulative_logistic_models():
    return {
        "v1+" + "+".join(groups): (
            partial(logistic_regression.fit, groups=groups),
            logistic_regression.predict,
        )
        for groups in ("A", "AB", "ABC", "ABCD")
    }


def fold_metadata(number, cutoff, excluded, train, test):
    sorted_test_ids = json.dumps(sorted(test["dispute_id"]), ensure_ascii=False)
    return {
        "fold": number, "cutoff": str(cutoff), "train_rows": len(train), "test_rows": len(test),
        "excluded_by_closure": excluded,
        "sorted_test_ids_sha256": hashlib.sha256(sorted_test_ids.encode("utf-8")).hexdigest(),
    }


def metrics(actual, probabilities):
    return {
        "auc": roc_auc_score(actual, probabilities) if len(set(actual)) == 2 else np.nan,
        "log_loss": log_loss(actual, probabilities, labels=[0, 1]),
        "brier": brier_score_loss(actual, probabilities),
    }


def calibration(actual, probabilities):
    frame = pd.DataFrame({"predicted": probabilities, "actual": actual})
    frame["bin"] = pd.cut(
        frame["predicted"], bins=np.linspace(0, 1, 11), include_lowest=True,
        labels=["[0.0, 0.1]"] + [f"({i / 10:.1f}, {(i + 1) / 10:.1f}]" for i in range(1, 10)],
    )
    return frame.groupby("bin", observed=False).agg(
        count=("actual", "size"),
        mean_prediction=("predicted", "mean"),
        actual_win_rate=("actual", "mean"),
    )


def score_summary(results):
    summary = results.groupby("model")[["auc", "log_loss", "brier"]].agg(
        ["mean", lambda values: values.std(ddof=0), "min", "max", "count"]
    )
    summary.columns = pd.MultiIndex.from_tuples([
        (metric, {"<lambda_0>": "std", "count": "defined_folds"}.get(stat, stat))
        for metric, stat in summary.columns
    ])
    return summary


def evaluate(frame, models, output_dir=None, *, include_model_details=True):
    results = []
    calibration_tables = []
    folds = []
    coefficients = []
    feature_lists = {}

    for number, cutoff, excluded, train, test in expanding_folds(frame):
        folds.append(fold_metadata(number, cutoff, excluded, train, test))
        print(f"\nFold {number}, cutoff {cutoff}")
        print(f"Training {len(train)}, test {len(test)}, training excluded by closure {excluded}")
        counts = pd.DataFrame({
            "train": train["evidence_submitted"].map(baseline.evidence_count).value_counts(),
            "test": test["evidence_submitted"].map(baseline.evidence_count).value_counts(),
        }).reindex(range(7)).fillna(0).astype(int)
        counts.index.name = "n_evidence (6 includes 6+)"
        print(counts.to_string())
        train_rows = train.to_dict("records")
        test_rows = test.drop(columns=["outcome", "closed_at"]).to_dict("records")
        actual = test["outcome"].eq("won").astype(int).to_numpy()
        reference = train["outcome"].eq("won").mean()
        predictions = {"constant": np.full(len(test), reference)}
        for name, (fit, predict) in models.items():
            model = fit(train_rows)
            predictions[name] = predict(model, test_rows)
            if name == "baseline":
                levels = Counter(item["level"] for item in baseline.predict_details(model, test_rows))
                print(f"Baseline fallback counts {dict(levels)}")
            if include_model_details and "pipeline" in model:
                feature_lists[f"{number}:{name}"] = model["pipeline"]["features"].get_feature_names_out().tolist()
            if include_model_details and name in {"logistic_regression", "v1+A+B+C+D"}:
                print("\nLogistic regression top coefficients by absolute size")
                for feature, coefficient in logistic_regression.top_coefficients(model):
                    print(f"  {feature:<40} {coefficient:+.6f}")
                    coefficients.append({"fold": number, "model": name, "feature": feature,
                                         "coefficient": float(coefficient)})
        for name, probabilities in predictions.items():
            scores = metrics(actual, probabilities)
            results.append({"fold": number, "model": name, **scores})
            print(f"\n{name} metrics {scores}")
            table = calibration(actual, probabilities)
            print(table.to_string(float_format=lambda x: f"{x:.4f}"))
            calibration_tables.append(table.reset_index().assign(fold=number, model=name))
    results = pd.DataFrame(results)
    print("\nPer-fold metrics (undefined AUC appears as NaN)")
    print(results.to_string(index=False))
    print("\nAcross-fold mean and spread (population standard deviation)")
    summary = score_summary(results)
    print(summary.to_string())
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        results.to_csv(output_dir / "scores.csv", index=False)
        summary.to_csv(output_dir / "summary.csv")
        pd.concat(calibration_tables).to_csv(output_dir / "calibration.csv", index=False)
        (output_dir / "folds.json").write_text(json.dumps(folds, indent=2) + "\n")
        if include_model_details:
            pd.DataFrame(coefficients).to_csv(output_dir / "coefficients.csv", index=False)
            (output_dir / "features.json").write_text(json.dumps(feature_lists, indent=2))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="Local disputes.csv path")
    parser.add_argument("--joined", action="store_true", help="Compare cumulative joined feature groups")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    models = {
        "baseline": (baseline.fit, baseline.predict),
        "logistic_regression": (logistic_regression.fit, logistic_regression.predict),
    }
    if args.joined:
        frame = load_joined_rows(args.csv_path)
        models = {"baseline": (baseline.fit, baseline.predict),
                  "v1": (logistic_regression.fit, logistic_regression.predict),
                  **cumulative_logistic_models()}
        if args.output_dir is None:
            args.output_dir = Path(__file__).resolve().parents[2] / "artifacts" / "joined_features_corrected"
    else:
        frame = load_rows(args.csv_path, extra_columns=("merchant_responded", "amount_usd"))
    evaluate(frame, models, args.output_dir)


