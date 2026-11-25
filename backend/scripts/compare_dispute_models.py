"""Compare dispute-stage candidates on the fixed expanding folds."""

import argparse
from decimal import Decimal
from functools import partial
import json
from pathlib import Path

from sklearn.ensemble import HistGradientBoostingClassifier

import deterministic_baseline as baseline
from evaluate_disputes import FOLD_EDGES, cumulative_logistic_models, evaluate, load_joined_rows
import logistic_regression


LOGISTIC_V1 = "v1"
ABLATION = "v1_without_merchant_responded"
BOOSTING_V1 = "hgb_v1"
BOOSTING_JOINED = "hgb_v1+A+B+C+D"
MINIMUM_GAIN = Decimal("0.01")
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "experiments" / "model_comparison"


def fit_boosting(rows, groups=()):
    classifier = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=200, early_stopping=False, random_state=42,
    )
    return logistic_regression.fit_classifier(rows, classifier, groups, scale_numeric=False)


def comparison_models():
    predict = logistic_regression.predict
    return {
        "baseline": (baseline.fit, baseline.predict),
        LOGISTIC_V1: (logistic_regression.fit, predict),
        **cumulative_logistic_models(),
        BOOSTING_V1: (fit_boosting, predict),
        BOOSTING_JOINED: (partial(fit_boosting, groups="ABCD"), predict),
        ABLATION: (partial(logistic_regression.fit, include_merchant_response=False), predict),
    }


def select_by_log_loss(scores, candidate_order):
    folds = tuple(range(1, len(FOLD_EDGES)))
    log_losses = scores.pivot(index="fold", columns="model", values="log_loss")
    reference = [Decimal(str(log_losses.at[fold, LOGISTIC_V1])) for fold in folds]
    candidates = {}
    eligible_means = {}
    # Iteration order breaks equal means.
    for name in candidate_order:
        losses = [Decimal(str(log_losses.at[fold, name])) for fold in folds]
        gains = [v1_loss - candidate_loss for v1_loss, candidate_loss in zip(reference, losses)]
        eligible = all(gain >= MINIMUM_GAIN for gain in gains)
        mean_loss = sum(losses) / len(folds)
        candidates[name] = {
            "eligible": eligible,
            "log_loss_gain_by_fold": dict(zip(folds, map(float, gains))),
            "mean_log_loss": float(mean_loss),
        }
        if eligible:
            eligible_means[name] = mean_loss

    selected = min(eligible_means, key=eligible_means.get, default=LOGISTIC_V1)
    return selected, candidates


def selection_decision(scores):
    selected, candidates = select_by_log_loss(scores, (BOOSTING_V1, BOOSTING_JOINED))
    return {
        "selected_model": selected,
        "reference_model": LOGISTIC_V1,
        "minimum_log_loss_gain_each_fold": float(MINIMUM_GAIN),
        "boosting_tie_break": BOOSTING_V1,
        "explanation_only_models": [ABLATION],
        "boosting_candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Local disputes.csv path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output_dir.exists() and (
        not args.output_dir.is_dir() or any(args.output_dir.iterdir())
    ):
        parser.error("Choose an empty output directory to preserve existing reports.")
    frame = load_joined_rows(args.csv_path)
    scores = evaluate(frame, comparison_models(), args.output_dir, include_model_details=False)
    result = json.dumps(selection_decision(scores), indent=2)
    (args.output_dir / "selection.json").write_text(result + "\n")
    print("\nModel selection")
    print(result)


if __name__ == "__main__":
    main()
