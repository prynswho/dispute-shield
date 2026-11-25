"""Fit and export the final flag-free payment-risk model and risk tiers."""

import argparse
import json
from math import ceil
from pathlib import Path

import joblib
import numpy as np

from evaluate_payment_risk import RISK_FOLD_EDGES, expanding_folds
from payment_risk import fit_logistic, predict
from payment_risk_features import LABEL, load_rows


def tier_cutoffs(scores):
    ranked = np.sort(np.asarray(scores, dtype=float))[::-1]
    if not len(ranked) or not np.isfinite(ranked).all():
        raise ValueError("Tier cutoffs require finite out-of-fold scores")
    high, medium = (float(ranked[ceil(len(ranked) * fraction) - 1])
                    for fraction in (0.02, 0.05))
    return {
        "high_min_score": high,
        "medium_min_score": medium,
        "high_rows": int((ranked >= high).sum()),
        "medium_rows": int(((ranked >= medium) & (ranked < high)).sum()),
        "scored_rows": len(ranked),
    }


def export(frame, output_dir):
    edges = RISK_FOLD_EDGES["three_folds"]
    scores = []
    for _, _, _, train, test in expanding_folds(frame, edges):
        model = fit_logistic(train.to_dict("records"), include_invoice_flags=False)
        scores.extend(predict(model, test.drop(columns=LABEL).to_dict("records")))
    tiers = {
        **tier_cutoffs(scores),
        "rule": "High at or above high_min_score, otherwise medium at or above medium_min_score, otherwise low.",
        "source": "Pooled out-of-fold predictions from the three-fold payment-risk layout.",
        "fold_edges": edges,
        "final_training_rows": len(frame),
    }

    model = fit_logistic(frame.to_dict("records"), include_invoice_flags=False)
    output_dir.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, output_dir / "model.joblib")
    joblib.dump(model["pipeline"]["features"], output_dir / "encoder.joblib")
    (output_dir / "tiers.json").write_text(json.dumps(tiers, indent=2) + "\n", encoding="utf-8")
    return tiers


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    frame, _ = load_rows(args.data_dir)
    print(json.dumps(export(frame, args.output_dir), indent=2))
