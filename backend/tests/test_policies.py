"""Policy arithmetic and API checks using synthetic aggregate counts."""

import csv
import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import features, policies
from app.catalog import REASONS
from app.main import app


def aggregate_input():
    rows = []
    for band in ("under_300", "300_or_more"):
        for address, lost, won, dollars in (("absent", 8, 2, 1000), ("present", 4, 6, 400)):
            rows.append({
                "address": address, "band": band, "invoices": 100,
                "invoices_with_payments": 100, "payments": 100,
                "lost": lost, "won": won, "open": 0, "withdrawn": 0, "usd_lost": dollars,
            })
    return {"groups": rows, "period": "Synthetic period", "source": "Made-up test counts",
            "missing_invoice_payments": 0}


def signed_aggregate_input():
    def outcomes(lost, won, principal):
        return {"lost": lost, "won": won, "open": 0, "withdrawn": 0, "lost_principal": principal}

    return {
        "period": "Synthetic period", "source": "Made-up test counts",
        "baseline": {"disputes": 100, "disputes_lost": 50, "usd_lost": 5000},
        "invoice_amount_gt": 1000,
        "invoice_counts": {
            "unsigned": {"paid": 80, "open": 2, "disputed": 30},
            "signed": {"paid": 80, "open": 2, "disputed": 23},
        },
        "excluded_benefit_reasons": ["duplicate"],
        "groups": [
            {"reason": "service_not_provided", "unsigned": outcomes(8, 2, 1000), "signed": outcomes(4, 6, 400)},
            {"reason": "fraud", "unsigned": outcomes(2, 8, 200), "signed": outcomes(8, 2, 800)},
            {"reason": "duplicate", "unsigned": outcomes(8, 2, 1000), "signed": outcomes(0, 3, 0)},
        ],
    }


class PolicyTests(unittest.TestCase):
    def test_attrition_precedes_evidence_and_bounds_order_numerically(self):
        result = policies.address_mandatory(aggregate_input())
        self.assertEqual(result["baseline"], {"disputes": 40, "disputes_lost": 24, "usd_lost": 2800})
        self.assertEqual(result["expected_jobs_lost"], 6)
        self.assertEqual(len(result["scenarios"]), 9)
        self.assertEqual(len({row["key"] for row in result["scenarios"]}), 9)
        conservative, central, optimistic = [
            row for row in result["scenarios"] if row["attrition_rate"] == 0.03
        ]
        self.assertEqual(conservative["change"], {"disputes": -0.6, "disputes_lost": -0.36, "usd_lost": -42})
        self.assertEqual(central["change"], {"disputes": -0.6, "disputes_lost": -4.3, "usd_lost": -534.5})
        self.assertEqual(optimistic["change"]["usd_lost"], -1027)
        dollars = next(row for row in result["results"] if row["metric"] == "usd_lost")
        self.assertEqual(dollars["low"], -1036)
        self.assertEqual(dollars["high"], -28)
        disputes = next(row for row in result["results"] if row["metric"] == "disputes")
        self.assertEqual(disputes, {
            "policy": "address_mandatory", "metric": "disputes",
            "estimated_change": -0.6, "low": -0.8, "high": -0.4,
        })
        for scenario in result["scenarios"]:
            for metric in policies.METRICS:
                self.assertAlmostEqual(
                    scenario["change"][metric],
                    scenario["attrition_change"][metric] + scenario["evidence_change"][metric],
                    places=2,
                )

    def test_no_observed_advantage_gives_no_evidence_benefit(self):
        data = aggregate_input()
        for group in data["groups"]:
            if group["address"] == "present":
                group.update(lost=9, won=1)
        result = policies.address_mandatory(data)
        for scenario in result["scenarios"]:
            self.assertEqual(scenario["evidence_change"]["usd_lost"], 0)
            self.assertAlmostEqual(scenario["change"]["disputes"], -20 * scenario["attrition_rate"])

    def test_attrition_and_evidence_are_varied_independently(self):
        result = policies.address_mandatory(aggregate_input())
        observed = {(row["attrition_rate"], row["gap_share"]) for row in result["scenarios"]}
        self.assertEqual(observed, {
            (rate, share) for rate in (0.02, 0.03, 0.04) for share in (0, 0.5, 1)
        })
        for row in result["scenarios"]:
            expected_avoided = (4 * (1 - row["attrition_rate"]) + 4) * row["gap_share"]
            self.assertEqual(row["change"]["disputes_lost"], round(
                -12 * row["attrition_rate"] - expected_avoided, 2,
            ))
            self.assertEqual(row["expected_jobs_lost"], 200 * row["attrition_rate"])

    def test_sparse_or_invalid_aggregates_fail_explicitly(self):
        data = aggregate_input()
        data["groups"].pop()
        with self.assertRaises(ValueError):
            policies.address_mandatory(data)
        data = aggregate_input()
        data["groups"][0]["lost"] = -1
        with self.assertRaises(ValueError):
            policies.address_mandatory(data)

    def test_registry_and_export_keep_the_brief_format(self):
        report = policies.address_mandatory(aggregate_input())
        client = TestClient(app)
        with patch("app.policies.evaluate_policies", return_value=[report]):
            response = client.get("/api/policies")
            self.assertEqual(response.json()["policies"][0]["baseline"]["disputes"], 40)
            export = client.get("/api/policies/whatif_results.csv")
        self.assertIn('filename="whatif_results.csv"', export.headers["content-disposition"])
        rows = list(csv.DictReader(io.StringIO(export.text)))
        self.assertEqual(len(rows), 3)
        self.assertEqual(list(rows[0]), ["policy", "metric", "estimated_change", "low", "high"])
        self.assertEqual(set(row["metric"] for row in rows), set(policies.METRICS))
        catalog = client.get("/api/catalog").json()
        self.assertEqual(catalog["reasons"], REASONS)
        self.assertEqual(catalog["policies"], list(policies.POLICIES))
        self.assertEqual(catalog["evidence_rules"], list(features.EVIDENCE_RULES))

    def test_an_evidence_rule_can_be_registered_as_a_function(self):
        self.assertIsNone(features.EVIDENCE_RULES["customer_address"](
            {"customer_address_present": "true"}, {}
        ))
        self.assertIn("service address", features.EVIDENCE_RULES["customer_address"](
            {"customer_address_present": "false"}, {}
        ))

    def test_signed_estimates_zero_attrition_and_reason_specific_savings(self):
        report = policies.signed_estimate_over_1000(signed_aggregate_input())
        conservative, central, optimistic = report["scenarios"]
        self.assertEqual(report["affected_invoices"], 112)
        self.assertEqual(report["expected_jobs_lost"], 0)
        self.assertEqual(conservative["change"], dict.fromkeys(policies.METRICS, 0))
        self.assertEqual(central["change"], {"disputes": 0, "disputes_lost": -2, "usd_lost": -300})
        self.assertEqual(optimistic["change"]["usd_lost"], -600)
        self.assertEqual(central["attrition_change"], dict.fromkeys(policies.METRICS, 0))
        for comparison in report["comparisons"][1:]:
            self.assertEqual(comparison["assumed_gap"], 0)
        self.assertEqual(report["results"][2]["low"], -600)
        self.assertEqual(report["results"][2]["high"], 0)
        self.assertTrue(any("before payment or dispute" in text for text in report["limitations"]))

    def test_signed_aggregates_require_correct_amount_scope_and_reconciliation(self):
        data = signed_aggregate_input()
        data["invoice_amount_gt"] = 999
        with self.assertRaises(ValueError):
            policies.signed_estimate_over_1000(data)
        data = signed_aggregate_input()
        data["invoice_counts"]["unsigned"]["disputed"] = 31
        with self.assertRaises(ValueError):
            policies.signed_estimate_over_1000(data)

    def test_export_includes_each_registered_policy_as_independent_rows(self):
        reports = [
            policies.address_mandatory(aggregate_input()),
            policies.signed_estimate_over_1000(signed_aggregate_input()),
        ]
        with patch("app.policies.evaluate_policies", return_value=reports):
            response = TestClient(app).get("/api/policies/whatif_results.csv")
        rows = list(csv.DictReader(io.StringIO(response.text)))
        self.assertEqual(len(rows), 6)
        self.assertEqual(set(row["policy"] for row in rows), set(policies.POLICIES))


if __name__ == "__main__":
    unittest.main()
