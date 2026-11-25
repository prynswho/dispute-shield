"""Policy calculations using approved aggregate inputs and explicit assumptions."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "policy_data"
OUTCOMES = ("won", "lost", "open", "withdrawn")
METRICS = ("disputes", "disputes_lost", "usd_lost")
ADDRESS_ATTRITION_RATES = (0.02, 0.03, 0.04)
SCENARIOS = [
    {"key": "conservative", "label": "Attrition only", "gap_share": 0.0},
    {"key": "central", "label": "Half the observed gap", "gap_share": 0.5},
    {"key": "optimistic", "label": "Full observed gap", "gap_share": 1.0},
]


def scenario_results(policy_key, baseline, attrition, evidence_cases, evidence_dollars, zero_label):
    scenarios = []
    for scenario in SCENARIOS:
        evidence = {
            "disputes": 0,
            "disputes_lost": evidence_cases * scenario["gap_share"],
            "usd_lost": evidence_dollars * scenario["gap_share"],
        }
        change = {metric: round(-attrition[metric] - evidence[metric], 2) for metric in METRICS}
        attrition_change = {metric: round(-value, 2) for metric, value in attrition.items()}
        scenarios.append({
            **scenario, "label": zero_label if scenario["gap_share"] == 0 else scenario["label"], "change": change,
            "after": {metric: round(baseline[metric] + change[metric], 2) for metric in METRICS},
            "attrition_change": attrition_change,
            "evidence_change": {
                metric: round(change[metric] - attrition_change[metric], 2) for metric in METRICS
            },
        })
    return scenarios, policy_metrics(policy_key, scenarios)


def policy_metrics(policy_key, scenarios):
    central = next(row for row in scenarios if row["key"] == "central")
    results = [{
        "policy": policy_key, "metric": metric,
        "estimated_change": central["change"][metric],
        "low": min(row["change"][metric] for row in scenarios),
        "high": max(row["change"][metric] for row in scenarios),
    } for metric in METRICS]
    return results


def address_mandatory(data):
    groups = data["groups"]
    indexed = {(row["address"], row["band"]): row for row in groups}
    expected = {(address, band) for address in ("absent", "present")
                for band in ("under_300", "300_or_more")}
    if set(indexed) != expected or len(groups) != 4:
        raise ValueError("Address policy requires one group per address status and amount band")
    for row in groups:
        counts = [row[key] for key in (*OUTCOMES, "invoices", "payments", "invoices_with_payments")]
        if any(value < 0 or int(value) != value for value in counts) or row["usd_lost"] < 0:
            raise ValueError("Policy counts and loss amounts must be nonnegative")
        if row["lost"] + row["won"] == 0:
            raise ValueError("Each address group needs resolved disputes")
    baseline = {
        "disputes": sum(sum(row[key] for key in OUTCOMES) for row in groups),
        "disputes_lost": sum(row["lost"] for row in groups),
        "usd_lost": sum(row["usd_lost"] for row in groups),
    }
    low_value = [row for row in groups if row["band"] == "under_300"]
    low_totals = {
        "disputes": sum(sum(row[key] for key in OUTCOMES) for row in low_value),
        "disputes_lost": sum(row["lost"] for row in low_value),
        "usd_lost": sum(row["usd_lost"] for row in low_value),
    }
    comparisons = []
    for band in ("under_300", "300_or_more"):
        absent, present = indexed["absent", band], indexed["present", band]
        resolved = absent["lost"] + absent["won"]
        absent_rate = absent["lost"] / resolved
        present_rate = present["lost"] / (present["lost"] + present["won"])
        gap = max(absent_rate - present_rate, 0)
        comparisons.append({
            "band": band, "absent_loss_rate": absent_rate, "present_loss_rate": present_rate,
            "gap": gap, "absent_resolved": resolved,
            "present_resolved": present["lost"] + present["won"],
        })
    scenarios = []
    for attrition_rate in ADDRESS_ATTRITION_RATES:
        attrition = {metric: attrition_rate * value for metric, value in low_totals.items()}
        evidence_cases = evidence_dollars = 0.0
        for comparison in comparisons:
            absent = indexed["absent", comparison["band"]]
            retained = 1 - attrition_rate if comparison["band"] == "under_300" else 1
            avoided = retained * comparison["absent_resolved"] * comparison["gap"]
            evidence_cases += avoided
            evidence_dollars += avoided * absent["usd_lost"] / absent["lost"] if absent["lost"] else 0
        rate_scenarios, _ = scenario_results(
            "address_mandatory", baseline, attrition, evidence_cases, evidence_dollars, "Attrition only",
        )
        for scenario in rate_scenarios:
            title = scenario["key"]
            scenario["title"] = title
            if attrition_rate != 0.03 or title != "central":
                scenario["key"] = f"attrition_{round(attrition_rate * 100)}_{title}"
            scenario["attrition_rate"] = attrition_rate
            scenario["expected_jobs_lost"] = round(
                attrition_rate * sum(row["invoices"] for row in low_value), 2,
            )
            scenarios.append(scenario)
    results = policy_metrics("address_mandatory", scenarios)
    central = next(row for row in scenarios if row["key"] == "central")
    return {
        "policy": "address_mandatory", "name": "Mandatory customer address",
        "description": "Require a customer address on every invoice.",
        "period": data["period"], "source": data["source"], "confidence": "Low",
        "baseline": {key: round(value, 2) for key, value in baseline.items()},
        "affected_invoices": sum(row["invoices"] for row in groups if row["address"] == "absent"),
        "expected_jobs_lost": central["expected_jobs_lost"],
        "excluded_payments": data["missing_invoice_payments"],
        "gap_description": "The gap is the observed difference in resolved loss rates for invoices with and without addresses.",
        "population_notes": [
            f"Jobs currently missing addresses ({sum(row['invoices'] for row in groups if row['address'] == 'absent'):,}) are affected by the evidence requirement.",
            f"Central expected jobs leaving ScanPay ({central['expected_jobs_lost']:,.2f}) use the 3% assumption across all jobs under $300.",
            "Attrition varies over 2%, 3%, and 4%, independently of evidence benefit. All nine combinations determine the scenario bounds.",
            "The evidence benefit applies after attrition, separately within each amount band.",
        ],
        "scenarios": scenarios, "results": results, "comparisons": comparisons,
        "assumptions": [
            "Central attrition is 3% of all jobs under $300, including jobs already showing an address. Sensitivity cases use 2% and 4%.",
            "The 2% to 4% range is an analyst-chosen sensitivity assumption around the brief's approximate 3%.",
            "Central estimates use 3% attrition and 50% gap closure. Bounds span all nine attrition and evidence combinations.",
            "Attrition removes disputes and losses proportionally within each amount band.",
            "Retained jobs have unchanged dispute incidence.",
            "Only retained jobs lacking addresses receive the assumed evidence benefit.",
            "Central benefit closes half the observed resolved-loss-rate gap, with zero and full closure as bounds.",
            "Avoided losses have the historical average lost amount plus $25 fee within their absent-address amount band.",
            "Open and withdrawn disputes receive no assumed outcome improvement.",
        ],
        "limitations": [
            "These are scenario bounds. They are not statistical confidence intervals.",
            "Invoice addresses are historical snapshot values. Their availability before a dispute is unverified.",
            "Team, job type, and other differences can explain the observed rate gap.",
            "Fifty-two payments without invoice matches are outside the supplied aggregate cohort.",
            "Job attrition can reduce payment volume. Revenue or margin impact is not included in dispute-loss savings.",
        ],
    }


def signed_estimate_over_1000(data):
    # This policy changes conditional loss outcomes only.
    # Dispute incidence and job attrition are both assumed unchanged.
    if data["invoice_amount_gt"] != 1000:
        raise ValueError("Signed-estimate aggregates must cover invoice amount strictly above $1,000")
    comparisons = []
    evidence_cases = evidence_dollars = 0.0
    counts = data["invoice_counts"]
    for status in ("unsigned", "signed"):
        total_disputes = sum(
            sum(group[status][outcome] for outcome in OUTCOMES) for group in data["groups"]
        )
        if total_disputes != counts[status]["disputed"]:
            raise ValueError("Per-reason dispute counts must reconcile with the invoice-status aggregates")
    for group in data["groups"]:
        unsigned, signed = group["unsigned"], group["signed"]
        for sample in (unsigned, signed):
            for outcome in OUTCOMES:
                count = sample[outcome]
                if count < 0 or int(count) != count:
                    raise ValueError("Dispute outcome counts must be nonnegative integers")
            if sample["lost_principal"] < 0:
                raise ValueError("Lost dispute principal must be nonnegative")
        unsigned_n = unsigned["lost"] + unsigned["won"]
        signed_n = signed["lost"] + signed["won"]
        unsigned_rate = unsigned["lost"] / unsigned_n if unsigned_n else None
        signed_rate = signed["lost"] / signed_n if signed_n else None
        gap = 0.0
        if unsigned_rate is not None and signed_rate is not None:
            gap = max(unsigned_rate - signed_rate, 0)
        if group["reason"] in data["excluded_benefit_reasons"]:
            gap = 0.0
        avoided = unsigned_n * gap
        evidence_cases += avoided
        if unsigned["lost"]:
            evidence_dollars += avoided * (unsigned["lost_principal"] / unsigned["lost"] + 25)
        comparisons.append({
            "reason": group["reason"],
            "unsigned_resolved": unsigned_n, "signed_resolved": signed_n,
            "unsigned_loss_rate": unsigned_rate, "signed_loss_rate": signed_rate,
            "assumed_gap": gap,
        })
    zero = dict.fromkeys(METRICS, 0)
    scenarios, results = scenario_results(
        "signed_estimate_over_1000", data["baseline"], zero,
        evidence_cases, evidence_dollars, "No evidence benefit",
    )
    return {
        "policy": "signed_estimate_over_1000",
        "name": "Signed estimates above $1,000",
        "description": "Require a signed estimate when invoice amount is strictly above $1,000.",
        "period": data["period"], "source": data["source"], "confidence": "Low",
        "baseline": data["baseline"], "baseline_scope": "Full months 1–22 historical portfolio",
        "affected_invoices": sum(counts["unsigned"].values()), "expected_jobs_lost": 0,
        "scenarios": scenarios, "results": results, "comparisons": comparisons,
        "gap_description": "The gap is the observed difference in resolved loss rates for unsigned and signed estimates within each dispute reason.",
        "population_notes": [
            f"Unsigned invoices above $1,000 ({sum(counts['unsigned'].values()):,}) are affected.",
            "Expected job-volume side effects are zero. Dispute incidence stays unchanged.",
            "Evidence benefit is calculated separately by dispute reason. The baseline covers the full historical portfolio.",
        ],
        "assumptions": [
            "Invoices of exactly $1,000 are outside the supplied eligible cohort.",
            "No job attrition, payment delay, or additional operating cost is assumed.",
            "Central benefit closes half the positive observed resolved-loss-rate gap within each reason. The bounds use zero and full closure.",
            "Fraud receives zero benefit because signed estimates had a higher observed loss rate.",
            "Duplicate receives zero benefit because its signed sample has only three resolved cases.",
            "Avoided losses use the unsigned group's average lost principal plus the $25 fee, separately by reason.",
            "Open and withdrawn disputes receive no assumed outcome change.",
            "Policies are evaluated independently. Their estimated savings must not be added without modelling overlap.",
        ],
        "limitations": [
            "Historical invoices are August 2026 snapshots. We cannot verify whether signed estimates were collected before payment or dispute.",
            "The observed win-rate difference may partly reflect later evidence collection or differences between jobs and teams.",
            "These are scenario bounds. They are not statistical confidence intervals.",
            "Credit-not-processed has only six resolved signed cases, so its estimated benefit is especially uncertain.",
            "The lower disputed share for signed invoices is observational. No reduction in dispute incidence is assumed.",
        ],
    }


POLICIES = {
    "address_mandatory": address_mandatory,
    "signed_estimate_over_1000": signed_estimate_over_1000,
}


def evaluate_policies(mode="open_expected"):
    from .policy_outcomes import MODES, apply_sensitivity

    if mode not in MODES:
        raise ValueError("Unknown policy outcome analysis mode")
    results = []
    for key, calculate in POLICIES.items():
        data = json.loads((DATA_DIR / f"{key}.json").read_text())
        results.append(calculate(data))
    if mode != "resolved_only":
        path = DATA_DIR / "outcome_sensitivity.json"
        if not path.exists():
            raise RuntimeError("Policy outcome aggregates are unavailable. Run prepare_policy_outcomes.py first.")
        aggregate = json.loads(path.read_text())
        results = [
            apply_sensitivity(report, aggregate["policies"][report["policy"]], mode, aggregate["counts"])
            for report in results
        ]
    else:
        for report in results:
            report["analysis_mode"] = mode
            report["baseline_label"] = "Observed resolved-loss baseline"
    return results
