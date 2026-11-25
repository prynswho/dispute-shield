"""Reproduce policy scenario reports from checked-in aggregate inputs."""

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.policies import evaluate_policies
from app.policy_outcomes import MODES

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "experiments" / "policies"


def save_reports(output_dir, mode):
    policies = evaluate_policies(mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "scenarios.json").write_text(json.dumps(policies, indent=2) + "\n")
    with (output_dir / "whatif_results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["policy", "metric", "estimated_change", "low", "high"],
        )
        writer.writeheader()
        writer.writerows(row for policy in policies for row in policy["results"])
    for policy in policies:
        print(f"{mode} / {policy['name']}")
        for row in policy["results"]:
            print(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", choices=(*MODES, "all"), default="all")
    args = parser.parse_args()
    modes = MODES if args.mode == "all" else (args.mode,)
    for mode in modes:
        save_reports(args.output_dir / mode, mode)
