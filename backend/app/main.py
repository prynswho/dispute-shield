"""Upload, score, and export Dispute Shield datasets."""

import csv
import io
import os
from pathlib import Path
from uuid import uuid4
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .connectors import files
from . import features, policies, scoring
from .catalog import REASONS
from .policy_outcomes import ANALYSES

app = FastAPI(title="Dispute Shield")
MIB = 1024 * 1024
MAX_FILE_BYTES = 40 * MIB
MAX_BATCH_BYTES = 80 * MIB
PAYMENT_EXPORT = [
    "payment_id", "invoice_win_prob", "payment_win_prob", "dispute_risk_tier",
    "dispute_risk_score", "expected_loss_usd",
]
DISPUTE_EXPORT = ["dispute_id", "win_prob", "recommendation"]
WHATIF_EXPORT = ["policy", "metric", "estimated_change", "low", "high"]
PolicyMode = Literal["resolved_only", "open_expected", "withdrawn_sensitivity"]


async def upload_content(upload):
    content = await upload.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, f"Each CSV must be at most {MAX_FILE_BYTES / MIB:g} MiB")
    return content


def session_or_404(run_id):
    try:
        return files.load_session(run_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Upload session was not found") from None


def score_or_error(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except (RuntimeError, FileNotFoundError) as error:
        raise HTTPException(503, str(error)) from None


def csv_response(rows, columns, filename):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(stream.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/uploads/payments")
async def upload_payments(
    invoices: UploadFile = File(...), photos: UploadFile = File(...), payments: UploadFile = File(...),
):
    blobs = [await upload_content(upload) for upload in (invoices, photos, payments)]
    if sum(map(len, blobs)) > MAX_BATCH_BYTES:
        raise HTTPException(413, f"The combined upload must be at most {MAX_BATCH_BYTES / MIB:g} MiB")
    invoice_rows = score_or_error(
        features.parse_csv, blobs[0], features.INVOICE_COLUMNS, "invoices.csv", "invoice_id",
        skip_blank_keys=True,
    )
    photo_rows = score_or_error(features.parse_csv, blobs[1], features.PHOTO_COLUMNS, "photos.csv", "photo_id")
    payment_rows = score_or_error(features.parse_csv, blobs[2], features.PAYMENT_COLUMNS, "payments.csv", "payment_id")
    if not payment_rows:
        raise HTTPException(422, "payments.csv must contain at least one payment")
    inputs, checklists = score_or_error(features.payment_features, payment_rows, invoice_rows, photo_rows)
    predicted = score_or_error(scoring.score_payments, payment_rows, inputs, checklists)
    session = {"run_id": uuid4().hex, "payments": predicted, "disputes": []}
    files.save_session(session)
    return session


@app.post("/api/uploads/{run_id}/disputes")
async def upload_disputes(run_id: str, disputes: UploadFile = File(...)):
    content = await upload_content(disputes)
    session = session_or_404(run_id)
    rows = score_or_error(features.parse_csv, content, features.DISPUTE_COLUMNS, "disputes.csv", "dispute_id")
    predicted = score_or_error(scoring.score_disputes, rows, session["payments"]) if rows else []
    session["disputes"] = predicted
    files.save_session(session)
    return {"run_id": run_id, "disputes": predicted}


@app.get("/api/uploads/{run_id}")
def get_upload(run_id: str):
    return session_or_404(run_id)


@app.get("/api/uploads/{run_id}/payment_predictions.csv")
def export_payments(run_id: str):
    return csv_response(session_or_404(run_id)["payments"], PAYMENT_EXPORT, "payment_predictions.csv")


@app.get("/api/uploads/{run_id}/dispute_predictions.csv")
def export_disputes(run_id: str):
    return csv_response(session_or_404(run_id)["disputes"], DISPUTE_EXPORT, "dispute_predictions.csv")


@app.get("/api/portfolio")
def portfolio():
    return files.portfolio()


@app.get("/api/catalog")
def catalog():
    return {
        "reasons": REASONS,
        "policies": list(policies.POLICIES),
        "evidence_rules": list(features.EVIDENCE_RULES),
    }


@app.get("/api/policies")
def policy_results(mode: PolicyMode = "open_expected"):
    return {
        "policies": score_or_error(policies.evaluate_policies, mode),
        "analysis_modes": [{"value": value, "label": label} for value, label in ANALYSES.items()],
    }


@app.get("/api/policies/whatif_results.csv")
def export_policies(mode: PolicyMode = "open_expected"):
    reports = score_or_error(policies.evaluate_policies, mode)
    rows = [row for policy in reports for row in policy["results"]]
    return csv_response(rows, WHATIF_EXPORT, "whatif_results.csv")


# The production container serves the React build from the same origin as the API.
frontend_dir = Path(os.environ.get("DISPUTE_FRONTEND_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
