"""Aggregate outcome sensitivity for open cases and optional withdrawn cases."""

from copy import deepcopy
import math

ANALYSES = {
    "open_expected": "Open cases probability weighted",
    "resolved_only": "Resolved-only reference",
    "withdrawn_sensitivity": "Include withdrawn-case sensitivity",
}
MODES = ("resolved_only", "open_expected", "withdrawn_sensitivity")
OPEN_TREATMENTS = ("all_won", "predicted", "all_lost")
TREATMENT_LABELS = {
    "all_won": "All open cases win",
    "predicted": "Probability weighted",
    "all_lost": "All open cases lose",
}
MONEY_METRICS = ("disputes_lost", "usd_lost")


def address_effect(row, report, scenario):
    low_value = row["invoice_amount"] < 300
    attrition = scenario["attrition_rate"] if low_value else 0
    band = "under_300" if low_value else "300_or_more"
    gap = next(item["gap"] for item in report["comparisons"] if item["band"] == band)
    evidence = gap * scenario["gap_share"] if not row["address_present"] else 0
    return attrition, evidence


def signed_estimate_effect(row, report, scenario):
    # This policy changes conditional loss outcomes only.
    # Dispute incidence and job attrition are both assumed unchanged.
    if row["invoice_amount"] <= 1000 or row["signed_estimate"]:
        return 0, 0
    gap = next((item["assumed_gap"] for item in report["comparisons"]
                if item["reason"] == row["reason"]), 0)
    return 0, gap * scenario["gap_share"]


OUTCOME_EFFECTS = {
    "address_mandatory": address_effect,
    "signed_estimate_over_1000": signed_estimate_effect,
}


def reference(report):
    return {
        "baseline": report["baseline"],
        "scenarios": [{
            "key": row["key"], "change": row["change"], "gap_share": row["gap_share"],
            "attrition_rate": row.get("attrition_rate", 0),
        } for row in report["scenarios"]],
    }


def build_sensitivity(reports, rows):
    """Consume scored rows in memory and return aggregates with no row identities."""
    for row in rows:
        if row["outcome"] not in {"open", "withdrawn"}:
            raise ValueError("Outcome sensitivity accepts only open or withdrawn cases")
        if not math.isfinite(row["win_prob"]) or not 0 <= row["win_prob"] <= 1:
            raise ValueError("Win probabilities must be finite and between zero and one")
        if not math.isfinite(row["amount_usd"]) or row["amount_usd"] <= 0:
            raise ValueError("Dispute amounts must be positive and finite")
    counts = {status: sum(row["outcome"] == status for row in rows) for status in ("open", "withdrawn")}
    output = {"counts": counts, "unscorable_rows": 0, "policies": {}}
    for report in reports:
        effect = OUTCOME_EFFECTS[report["policy"]]
        modes = {}
        for mode in MODES[1:]:
            scenarios = []
            for scenario in report["scenarios"]:
                for treatment in OPEN_TREATMENTS:
                    baseline_add = dict.fromkeys(MONEY_METRICS, 0.0)
                    attrition_add = dict.fromkeys(MONEY_METRICS, 0.0)
                    evidence_add = dict.fromkeys(MONEY_METRICS, 0.0)
                    for row in rows:
                        if row["outcome"] == "withdrawn" and mode == "open_expected":
                            continue
                        loss_probability = 1 - row["win_prob"]
                        if row["outcome"] == "open" and treatment != "predicted":
                            loss_probability = 0 if treatment == "all_won" else 1
                        attrition, reduction = effect(row, report, scenario)
                        # Bound the case's counterfactual loss probability between 0 and 1.
                        counterfactual = min(1, max(0, loss_probability - reduction))
                        avoided = (1 - attrition) * (loss_probability - counterfactual)
                        for metric, multiplier in (
                            ("disputes_lost", 1), ("usd_lost", row["amount_usd"] + 25),
                        ):
                            baseline_add[metric] += loss_probability * multiplier
                            attrition_add[metric] += attrition * loss_probability * multiplier
                            evidence_add[metric] += avoided * multiplier
                    scenarios.append({
                        "reference_key": scenario["key"], "open_treatment": treatment,
                        "baseline_add": baseline_add, "attrition_add": attrition_add,
                        "evidence_add": evidence_add,
                    })
            modes[mode] = scenarios
        output["policies"][report["policy"]] = {"reference": reference(report), "modes": modes}
    return output


def apply_sensitivity(report, aggregate, mode, counts):
    if aggregate["reference"] != reference(report):
        raise RuntimeError("Policy outcome aggregates are stale. Run prepare_policy_outcomes.py again.")
    output = deepcopy(report)
    originals = {row["key"]: row for row in report["scenarios"]}
    scenarios = []
    for addition in aggregate["modes"][mode]:
        original = originals[addition["reference_key"]]
        treatment = addition["open_treatment"]
        central = original["key"] == "central" and treatment == "predicted"
        scenario = {
            **original,
            "key": "central" if central else f"{original['key']}_{treatment}",
            "open_treatment": treatment,
            "open_treatment_label": TREATMENT_LABELS[treatment],
            "baseline": dict(report["baseline"]),
            "change": dict(original["change"]),
            "attrition_change": dict(original["attrition_change"]),
            "evidence_change": dict(original["evidence_change"]),
            "after": dict(original["after"]),
        }
        for metric in MONEY_METRICS:
            baseline = report["baseline"][metric] + addition["baseline_add"][metric]
            attrition = original["attrition_change"][metric] - addition["attrition_add"][metric]
            # Keep full precision additions until display rounding.
            change = original["change"][metric] - addition["attrition_add"][metric] - addition["evidence_add"][metric]
            scenario["baseline"][metric] = round(baseline, 2)
            scenario["change"][metric] = round(change, 2)
            scenario["attrition_change"][metric] = round(attrition, 2)
            scenario["evidence_change"][metric] = round(
                scenario["change"][metric] - scenario["attrition_change"][metric], 2,
            )
            scenario["after"][metric] = round(baseline + change, 2)
        scenarios.append(scenario)
    central = next(row for row in scenarios if row["key"] == "central")
    output.update(
        analysis_mode=mode, resolved_baseline=report["baseline"], baseline=central["baseline"],
        baseline_label="Expected baseline with probability-weighted outcomes",
        scenarios=scenarios, outcome_counts=counts,
    )
    output["results"] = [{
        "policy": report["policy"], "metric": metric,
        "estimated_change": central["change"][metric],
        "low": min(row["change"][metric] for row in scenarios),
        "high": max(row["change"][metric] for row in scenarios),
    } for metric in ("disputes", *MONEY_METRICS)]
    output["population_notes"] += [
        "Baseline shown uses predicted open outcomes. Each scenario has a baseline using the same outcome treatment as its counterfactual.",
        "The range combines policy assumptions with all-won, predicted, and all-lost open outcomes.",
    ]
    output["assumptions"] = [
        text for text in output["assumptions"] if not text.startswith("Open and withdrawn disputes receive")
    ] + [
        "Won and lost outcomes are fixed. Open cases add one minus predicted win probability as expected losses.",
        "Expected open-case dollars lost use disputed amount plus $25 multiplied by loss probability.",
        "Policy evidence reduces each unresolved case's loss probability by its group's gap times scenario benefit, capped at zero.",
        "Each case remains counted as a dispute under every outcome treatment. Existing attrition assumptions alone change dispute counts.",
    ]
    if mode == "withdrawn_sensitivity":
        output["assumptions"].append("Withdrawn cases are assigned predicted outcomes in this sensitivity mode.")
        output["limitations"].append(
            "Withdrawn-case probabilities are unvalidated because the model trained on won and lost cases. This mode reinterprets recorded withdrawals."
        )
    else:
        output["assumptions"].append("Withdrawn cases retain zero observed loss and receive no evidence benefit.")
    output["limitations"] += [
        "Probabilities for open cases are extrapolated from resolved disputes. Follow-up and selection differences can affect calibration.",
        "The point estimate is an expectation. The range spans explicit scenarios rather than a statistical confidence interval.",
    ]
    return output
