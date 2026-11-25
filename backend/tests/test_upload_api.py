"""End-to-end API checks using generated CSVs and fitted synthetic artifacts."""

import csv
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import joblib
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app import features, scoring

import early_win
import logistic_regression
import payment_risk


def csv_file(rows, columns=None):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def fixtures():
    invoices = [{
        "invoice_id": "i1", "team_id": "t1", "customer_id": "c1", "job_type": "repair",
        "line_item_count": "2", "customer_address_present": "false", "signed_estimate": "true",
        "terms_accepted": "true", "completion_signature": "false",
    }]
    payments = [{
        "payment_id": "p1", "invoice_id": "i1", "team_id": "t1", "customer_id": "c1",
        "collected_at": "2026-09-02T10:00:00Z", "amount_usd": "100", "tip_usd": "0",
        "payment_method": "chip", "card_country": "US", "card_type": "credit", "avs_result": "not_checked",
        "cvv_result": "not_checked", "receipt_sent": "true",
    }]
    photos = [
        {"photo_id": "ph1", "invoice_id": "i1", "kind": "after", "uploaded_at": "2026-09-02T10:00:00Z"},
        {"photo_id": "ph2", "invoice_id": "i1", "kind": "after", "uploaded_at": "2026-09-02T10:00:01Z"},
    ]
    disputes = [{
        "dispute_id": "d1", "payment_id": "p1", "invoice_id": "i1", "team_id": "t1",
        "opened_at": "2026-09-05", "reason": "fraud", "amount_usd": "100",
        "merchant_responded": "true", "evidence_submitted": "receipt",
    }]
    return invoices, payments, photos, disputes


class UploadApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            "DISPUTE_UPLOAD_DIR": str(root / "uploads"), "DISPUTE_ARTIFACT_DIR": str(root / "artifacts"),
        })
        self.environment.start()
        artifacts = root / "artifacts"
        (artifacts / "payment_risk").mkdir(parents=True)
        self.invoices, self.payments, self.photos, self.disputes = fixtures()
        inputs, _ = features.payment_features(self.payments, self.invoices, self.photos)
        training = [{**inputs[0], "has_dispute": i % 2, "outcome": "won" if i % 2 else "lost"} for i in range(30)]
        joblib.dump(payment_risk.fit_logistic(training, include_invoice_flags=False), artifacts / "payment_risk/model.joblib")
        joblib.dump({"invoice_win_prob": None, "payment_win_prob": early_win.fit(training, stage="payment")}, artifacts / "early_win.joblib")
        joblib.dump(logistic_regression.fit([
            {**self.disputes[0], "outcome": "won" if i % 2 else "lost"} for i in range(30)
        ]), artifacts / "dispute_win.joblib")
        (artifacts / "payment_risk/tiers.json").write_text(json.dumps({"high_min_score": 0.4, "medium_min_score": 0.2}))
        self.client = TestClient(app)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def upload(self):
        return self.client.post("/api/uploads/payments", files={
            "invoices": ("invoices.csv", csv_file(self.invoices)),
            "payments": ("payments.csv", csv_file(self.payments)),
            "photos": ("photos.csv", csv_file(self.photos)),
        })

    def test_complete_upload_score_export_and_reload(self):
        inputs, _ = features.payment_features(self.payments, self.invoices, self.photos)
        self.assertEqual(inputs[0]["photos_after_at_payment"], 1)
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        run = response.json()
        payment = run["payments"][0]
        self.assertIsNone(payment["invoice_win_prob"])
        self.assertEqual(payment["dispute_risk_tier"], "high")
        self.assertAlmostEqual(payment["expected_loss_usd"], payment["dispute_risk_score"] * (1-payment["payment_win_prob"]) * 125)
        self.assertIn("Add the service address", " ".join(payment["actions"]))
        step2 = self.client.post(f'/api/uploads/{run["run_id"]}/disputes', files={"disputes": ("disputes.csv", csv_file(self.disputes))})
        self.assertEqual(step2.status_code, 200, step2.text)
        self.assertIsNone(step2.json()["disputes"][0]["outcome"])
        export = self.client.get(f'/api/uploads/{run["run_id"]}/payment_predictions.csv')
        rows = list(csv.DictReader(io.StringIO(export.text)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invoice_win_prob"], "")
        export = self.client.get(f'/api/uploads/{run["run_id"]}/dispute_predictions.csv')
        self.assertEqual(export.text.splitlines()[0], "dispute_id,win_prob,recommendation")
        recovered = TestClient(app).get(f'/api/uploads/{run["run_id"]}').json()
        self.assertEqual(recovered["disputes"][0]["dispute_id"], "d1")

    def test_invalid_replacement_preserves_session_and_cross_run_fails(self):
        run_id = self.upload().json()["run_id"]
        self.disputes[0]["payment_id"] = "p-absent"
        response = self.client.post(f"/api/uploads/{run_id}/disputes", files={"disputes": ("d.csv", csv_file(self.disputes))})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"/api/uploads/{run_id}").json()["disputes"], [])
        self.assertEqual(self.client.get("/api/uploads/invalid").status_code, 404)

    def test_recommendation_boundary_and_limits(self):
        self.assertEqual(scoring.recommendation(15/125, 100), "accept")
        self.assertEqual(scoring.recommendation(0.13, 100), "fight")
        with patch("app.main.MAX_FILE_BYTES", 10):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/portfolio").json(), {"reasons": [], "teams": []})

    def test_upload_keeps_payments_with_blank_and_absent_invoice_ids(self):
        self.payments += [
            {**self.payments[0], "payment_id": "p-blank", "invoice_id": ""},
            {**self.payments[0], "payment_id": "p-unmatched", "invoice_id": "absent"},
        ]
        self.invoices.append({**self.invoices[0], "invoice_id": ""})
        self.photos.append({**self.photos[0], "photo_id": "orphan", "invoice_id": "absent"})
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        run = response.json()
        matched, blank, absent = run["payments"]
        self.assertIsNotNone(matched["dispute_risk_score"])
        self.assertIn("missing invoice ID", blank["actions"][0])
        self.assertIn("matching invoice", absent["actions"][0])
        for row in (blank, absent):
            for field in ("dispute_risk_tier", "dispute_risk_score", "payment_win_prob", "expected_loss_usd"):
                self.assertIsNone(row[field])
        export = self.client.get(f'/api/uploads/{run["run_id"]}/payment_predictions.csv')
        rows = list(csv.DictReader(io.StringIO(export.text)))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["dispute_risk_tier"], "")


if __name__ == "__main__":
    unittest.main()
