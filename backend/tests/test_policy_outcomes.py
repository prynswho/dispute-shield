"""Outcome sensitivity checks with made-up counts and probabilities only."""

from copy import deepcopy
import math
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.policies import address_mandatory, signed_estimate_over_1000
from app.policy_outcomes import apply_sensitivity, build_sensitivity
from test_policies import aggregate_input, signed_aggregate_input


def report_pair():
    return [address_mandatory(aggregate_input()), signed_estimate_over_1000(signed_aggregate_input())]


def case(outcome="open", win_prob=0.8, invoice_amount=200):
    return {
        "outcome": outcome, "win_prob": win_prob, "amount_usd": 100,
        "invoice_amount": invoice_amount, "address_present": False,
        "signed_estimate": False, "reason": "service_not_provided",
    }


class OutcomeSensitivityTests(unittest.TestCase):
    def test_expected_baseline_and_counterfactual_use_same_probability(self):
        report = report_pair()[0]
        aggregate = build_sensitivity([report], [case()])
        modeled = apply_sensitivity(report, aggregate["policies"][report["policy"]],
                                    "open_expected", aggregate["counts"])
        original = next(row for row in report["scenarios"] if row["key"] == "central")
        central = next(row for row in modeled["scenarios"] if row["key"] == "central")
        self.assertAlmostEqual(modeled["baseline"]["disputes_lost"], report["baseline"]["disputes_lost"] + .2)
        self.assertEqual(modeled["baseline"]["usd_lost"], report["baseline"]["usd_lost"] + 25)
        self.assertEqual(central["change"]["disputes"], original["change"]["disputes"])
        self.assertAlmostEqual(central["change"]["disputes_lost"], original["change"]["disputes_lost"] - .2)
        self.assertEqual(central["after"]["usd_lost"], original["after"]["usd_lost"])
        self.assertEqual(len(modeled["scenarios"]), 27)

    def test_zero_evidence_benefit_cannot_create_savings_from_baseline_addition(self):
        report = report_pair()[1]
        aggregate = build_sensitivity([report], [case(invoice_amount=2000)])
        modeled = apply_sensitivity(report, aggregate["policies"][report["policy"]],
                                    "open_expected", aggregate["counts"])
        no_benefit = [row for row in modeled["scenarios"] if row["gap_share"] == 0]
        for scenario in no_benefit:
            self.assertEqual(scenario["change"], dict.fromkeys(("disputes", "disputes_lost", "usd_lost"), 0))
            self.assertEqual(scenario["after"], scenario["baseline"])

    def test_withdrawn_treatment_is_opt_in_and_never_changes_dispute_incidence(self):
        report = report_pair()[1]
        aggregate = build_sensitivity([report], [case("withdrawn", .75, 2000)])
        payload = aggregate["policies"][report["policy"]]
        main = apply_sensitivity(report, payload, "open_expected", aggregate["counts"])
        sensitivity = apply_sensitivity(report, payload, "withdrawn_sensitivity", aggregate["counts"])
        self.assertEqual(main["baseline"], report["baseline"])
        self.assertEqual(sensitivity["baseline"]["usd_lost"], report["baseline"]["usd_lost"] + 31.25)
        for scenario in sensitivity["scenarios"]:
            self.assertEqual(scenario["change"]["disputes"], 0)
        self.assertTrue(any("unvalidated" in text for text in sensitivity["limitations"]))

    def test_endpoint_probabilities_and_policy_threshold_keep_bounds_valid(self):
        report = report_pair()[1]
        rows = [case(win_prob=1, invoice_amount=2000), case(win_prob=0, invoice_amount=1000)]
        aggregate = build_sensitivity([report], rows)
        modeled = apply_sensitivity(report, aggregate["policies"][report["policy"]],
                                    "open_expected", aggregate["counts"])
        central = next(row for row in modeled["scenarios"] if row["key"] == "central")
        original = next(row for row in report["scenarios"] if row["key"] == "central")
        self.assertEqual(central["change"], original["change"])
        for scenario in modeled["scenarios"]:
            self.assertGreaterEqual(scenario["after"]["disputes_lost"], 0)
            self.assertGreaterEqual(scenario["after"]["usd_lost"], 0)

    def test_stale_aggregate_and_invalid_probabilities_fail(self):
        report = report_pair()[0]
        aggregate = build_sensitivity([report], [case()])
        stale = deepcopy(report)
        stale["baseline"]["usd_lost"] += 1
        with self.assertRaisesRegex(RuntimeError, "stale"):
            apply_sensitivity(stale, aggregate["policies"][report["policy"]],
                              "open_expected", aggregate["counts"])
        for value in (-.1, 1.1, math.nan):
            with self.assertRaises(ValueError):
                build_sensitivity([report], [case(win_prob=value)])

    def test_api_and_csv_accept_mode_without_mixing_it_into_columns(self):
        client = TestClient(app)
        report = report_pair()[0]
        aggregate = build_sensitivity([report], [case()])
        modeled = apply_sensitivity(report, aggregate["policies"][report["policy"]],
                                    "open_expected", aggregate["counts"])
        with patch("app.policies.evaluate_policies", return_value=[modeled]) as calculate:
            response = client.get("/api/policies?mode=withdrawn_sensitivity")
            self.assertEqual(response.status_code, 200)
            calculate.assert_called_with("withdrawn_sensitivity")
            export = client.get("/api/policies/whatif_results.csv?mode=open_expected")
            self.assertEqual(export.text.splitlines()[0], "policy,metric,estimated_change,low,high")
        self.assertEqual(client.get("/api/policies?mode=unknown").status_code, 422)


if __name__ == "__main__":
    unittest.main()
