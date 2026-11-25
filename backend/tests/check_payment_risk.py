"""Run with PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_payment_risk.py."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from evaluate_payment_risk import expanding_folds
import payment_risk
import payment_risk_features as source


def write_data(folder):
    start = pd.Timestamp("2026-05-01", tz="UTC")
    payments = []
    invoices = []
    disputes = []
    outcomes = ["open", "withdrawn", "lost", "won"]
    for number in range(80):
        time = start + pd.Timedelta(hours={40: 39, 60: 59}.get(number, number))
        if number == 79:
            time = "2026-06-01T05:29:59.999999+05:30"
        payments.append({
            "payment_id": f"fake-p{number:02}",
            "invoice_id": f"fake-i{2 if number == 3 else number:02}",
            "team_id": "fake-team",
            "collected_at": str(time),
            "amount_usd": 100 + number,
            "tip_usd": "0",
            "receipt_sent": "true",
            "payment_method": "ach" if number == 0 else "tap",
            "card_country": {0: "", 1: "US", 2: "CA", 3: " NA "}.get(number, "US"),
            "card_type": "" if number == 0 else "credit",
            "avs_result": {0: "", 2: " not_checked "}.get(number, "match"),
            "cvv_result": "" if number == 0 else "match",
            "card_fingerprint": f"fake-card-{number}",
        })
        invoices.append({
            "invoice_id": f"fake-i{number:02}",
            "team_id": "fake-team",
            "job_type": "fixture_job" if number < 39 else "held_out_job",
            "line_item_count": number % 4 + 1,
            **{flag: "true" if (number % 3 == 0) else "false" for flag in source.INVOICE_FLAGS},
            "invoice_status": "future_status",
            "updated_at": "2099-01-01T00:00:00Z",
            "photos_before_count": 99,
            "photos_after_count": 99,
        })
        if number < 4 or number % 5 == 0:
            disputes.append({"payment_id": f"fake-p{number:02}", "outcome": outcomes[number % 4]})

    payments.extend([
        {**payments[1], "payment_id": "fake-cutoff", "collected_at": "2026-06-01T05:30:00+05:30"},
        {**payments[1], "payment_id": "fake-after", "collected_at": "2026-06-01T00:00:01Z"},
        {**payments[1], "payment_id": "fake-no-invoice", "invoice_id": "fake-absent"},
    ])
    disputes.extend([
        {"payment_id": "fake-p00", "outcome": "withdrawn"},
        {"payment_id": "fake-no-invoice", "outcome": "open"},
        {"payment_id": "fake-other", "outcome": "won"},
    ])
    photos = [
        {"photo_id": "fake-ph1", "invoice_id": "fake-i02", "kind": "before", "uploaded_at": "2026-05-01T01:00:00Z"},
        {"photo_id": "fake-ph2", "invoice_id": "fake-i02", "kind": "after", "uploaded_at": "2026-05-01T02:00:00Z"},
        {"photo_id": "fake-ph3", "invoice_id": "fake-i02", "kind": "after", "uploaded_at": "2026-05-01T03:00:00Z"},
        {"photo_id": "fake-ph4", "invoice_id": "fake-i02", "kind": "before", "uploaded_at": "2026-05-01T03:00:01Z"},
    ]
    for table, records in (("payments", payments[::-1]), ("invoices", invoices), ("photos", photos), ("disputes", disputes)):
        pd.DataFrame(records).to_csv(folder / f"{table}.csv", index=False)


class PaymentRiskTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        write_data(self.folder)

    def test_cohort_labels_and_point_in_time_photos(self):
        frame, cohort = source.load_rows(self.folder)
        rows = frame.set_index("payment_id")
        self.assertEqual(cohort["payment_rows_read"], 83)
        self.assertEqual(cohort["payments_before_collection_end"], 81)
        self.assertEqual(cohort["payments_excluded_on_or_after_collection_end"], 2)
        self.assertEqual(cohort["payments_excluded_missing_invoice"], 1)
        self.assertEqual(cohort["payments_eligible"], 80)
        self.assertEqual(cohort["eligible_payments_with_dispute"], 19)
        self.assertTrue(rows.loc["fake-p79", "collected_at"] < source.COLLECTION_END)
        self.assertEqual(rows.loc[["fake-p00", "fake-p01", "fake-p02", "fake-p03", "fake-p04"], source.LABEL].tolist(),
                         [1, 1, 1, 1, 0])
        self.assertEqual(rows.loc[["fake-p00", "fake-p01", "fake-p02", "fake-p03"], "card_country"].tolist(),
                         ["na", "us", "foreign", "na"])
        self.assertEqual(rows.loc[["fake-p00", "fake-p02"], "avs_result"].tolist(), ["na", "not_checked"])
        self.assertAlmostEqual(rows.loc["fake-p02", "log_amount_usd"], np.log(102))
        counts = ["photos_before_at_payment", "photos_after_at_payment"]
        self.assertEqual(rows.loc[["fake-p02", "fake-p03", "fake-p04"], counts].values.tolist(),
                         [[1, 1], [1, 2], [0, 0]])
        self.assertFalse(source.FORBIDDEN.intersection(frame.columns) - {"payment_id", "collected_at", source.LABEL})

    def test_invalid_join_keys_do_not_expand_the_cohort(self):
        source_file = self.folder / "invoices.csv"
        invoices = pd.read_csv(source_file)
        pd.concat([invoices, invoices.iloc[[2]]]).to_csv(source_file, index=False)
        with self.assertRaisesRegex(ValueError, "unique populated keys"):
            source.load_rows(self.folder)
        invoices.loc[2, "team_id"] = "fake-other-team"
        invoices.to_csv(source_file, index=False)
        with self.assertRaisesRegex(ValueError, "team IDs"):
            source.load_rows(self.folder)

    def test_flags_and_forbidden_columns_are_explicit(self):
        for forbidden in ("invoice_status", "updated_at", "photos_before_count", "photos_after_count", "dispute_id"):
            with self.subTest(forbidden=forbidden):
                with patch.object(source, "NUMERIC", (*source.NUMERIC, forbidden)):
                    with self.assertRaisesRegex(AssertionError, forbidden):
                        source.feature_columns()
        with_flags = source.feature_columns()
        without_flags = source.feature_columns(include_invoice_flags=False)
        self.assertEqual(set(with_flags["binary"]) - set(without_flags["binary"]), set(source.INVOICE_FLAGS))
        self.assertEqual(with_flags["categorical"], without_flags["categorical"])
        self.assertEqual(with_flags["numeric"], without_flags["numeric"])

    def test_lookup_minimum_and_smoothing(self):
        rows = [
            {"payment_method": method, "avs_result": avs, source.LABEL: int(i < disputed)}
            for method, avs, total, disputed in [("tap", "match", 20, 5), ("tap", "no_match", 10, 6), ("ach", "na", 10, 2)]
            for i in range(total)
        ]
        queries = [
            {"payment_method": "tap", "avs_result": "match"},
            {"payment_method": "tap", "avs_result": "no_match"},
            {"payment_method": "ach", "avs_result": "na"},
        ]
        self.assertEqual(payment_risk.predict_lookup(payment_risk.fit_lookup(rows), queries),
                         [6 / 22, 12 / 32, 14 / 42])

    def test_tied_folds_and_training_only_encoding(self):
        frame, _ = source.load_rows(self.folder)
        first, second = expanding_folds(frame)
        _, first_cutoff, first_end, first_train, first_test = first
        _, second_cutoff, second_end, second_train, second_test = second
        self.assertEqual([len(rows) for rows in (first_train, first_test, second_train, second_test)], [39, 20, 59, 21])
        self.assertEqual(first_end, second_cutoff)
        self.assertIsNone(second_end)
        self.assertLess(first_train["collected_at"].max(), first_cutoff)
        self.assertLess(first_test["collected_at"].max(), second_cutoff)
        self.assertTrue({"fake-p39", "fake-p40"}.issubset(set(first_test["payment_id"])))
        self.assertTrue({"fake-p59", "fake-p60"}.issubset(set(second_test["payment_id"])))
        self.assertTrue(set(first_test["payment_id"]).isdisjoint(second_test["payment_id"]))

        for fit in (payment_risk.fit_logistic, payment_risk.fit_hgb):
            train_rows = first_train.to_dict("records")
            model = fit(train_rows)
            encoder = model["pipeline"]["features"].named_transformers_["categorical"]
            self.assertEqual(encoder.categories_[model["columns"]["categorical"].index("job_type")].tolist(),
                             ["fixture_job"])
            test_rows = first_test.drop(columns=source.LABEL).to_dict("records")
            raw_predictions = payment_risk.predict(model, test_rows)
            poisoned = [{**row, "updated_at": "2100-01-01", "photos_before_count": 300} for row in test_rows]
            self.assertEqual(payment_risk.predict(model, poisoned), raw_predictions)
            self.assertEqual(len(raw_predictions), len(first_test))
            self.assertTrue(all(0 <= probability <= 1 for probability in raw_predictions))
            without_flags = fit(train_rows, include_invoice_flags=False)
            stripped = [{name: value for name, value in row.items() if name not in source.INVOICE_FLAGS}
                        for row in test_rows]
            self.assertEqual(without_flags["columns"]["binary"], ("receipt_sent",))
            self.assertEqual(payment_risk.predict(without_flags, test_rows), payment_risk.predict(without_flags, stripped))

    def test_cli_writes_aggregate_only_reports(self):
        output = self.folder / "reports"
        script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_payment_risk.py"
        result = subprocess.run(
            [sys.executable, str(script), str(self.folder), "--output-dir", str(output)],
            check=True, capture_output=True, text=True,
        )
        scores = pd.read_csv(output / "scores.csv")
        models = {"constant", "lookup", "logistic_with_flags", "logistic_without_flags",
                  "hgb_with_flags", "hgb_without_flags"}
        self.assertEqual(set(scores["model"]), models)
        self.assertEqual(scores.groupby("model")["fold"].apply(list).to_dict(), dict.fromkeys(models, [1, 2]))
        self.assertEqual(set(pd.read_csv(output / "invoice_flags_delta.csv")["fold"]), {"1", "2", "mean"})
        calibration = pd.read_csv(output / "calibration.csv")
        self.assertEqual(calibration.groupby(["fold", "model"]).size().tolist(), [10] * 12)
        for fold, group in calibration.groupby("fold"):
            self.assertEqual(set(group.groupby("model")["count"].sum()), {20 if fold == 1 else 21})
        folds = json.loads((output / "folds.json").read_text())
        frame, _ = source.load_rows(self.folder)
        for report, (_, _, _, _, test) in zip(folds, expanding_folds(frame), strict=True):
            ids = json.dumps(sorted(test["payment_id"]), ensure_ascii=False)
            self.assertEqual(report["sorted_test_ids_sha256"], hashlib.sha256(ids.encode("utf-8")).hexdigest())
            self.assertEqual(report["test_dispute_rate"], test[source.LABEL].mean())
        metadata = json.loads((output / "metadata.json").read_text())
        self.assertEqual(metadata["cohort"]["payments_excluded_missing_invoice"], 1)
        self.assertNotIn("fake-p", result.stdout)
        self.assertTrue(all("fake-p" not in report.read_text() for report in output.iterdir()))


if __name__ == "__main__":
    unittest.main()
