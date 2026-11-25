"""Build the payment-level dispute-risk cohort from local CSVs."""

from pathlib import Path

import numpy as np
import pandas as pd

from joined_features import boolean_values, photo_counts, read_table


COLLECTION_END = pd.Timestamp("2026-06-01", tz="UTC")
LABEL = "has_dispute"
PAYMENT_CATEGORIES = ("payment_method", "card_country", "card_type", "avs_result", "cvv_result")
INVOICE_FLAGS = (
    "customer_address_present", "customer_email_present", "customer_phone_present",
    "signed_estimate", "terms_accepted", "tech_gps_checkin", "completion_signature",
)
NUMERIC = (
    "log_amount_usd", "tip_usd", "line_item_count",
    "photos_before_at_payment", "photos_after_at_payment",
)
FORBIDDEN = {
    "invoice_status", "updated_at", "photos_before_count", "photos_after_count",
    "payment_id", "invoice_id", "team_id", "customer_id", "card_fingerprint",
    "collected_at", "created_at", "job_completed_at", "uploaded_at",
    "dispute_id", "opened_at", "closed_at", "reason", "outcome",
    "merchant_responded", "evidence_submitted", LABEL,
}


def feature_columns(include_invoice_flags=True):
    columns = {
        "categorical": (*PAYMENT_CATEGORIES, "job_type"),
        "numeric": NUMERIC,
        "binary": ("receipt_sent", *INVOICE_FLAGS) if include_invoice_flags else ("receipt_sent",),
    }
    forbidden = FORBIDDEN.intersection(name for group in columns.values() for name in group)
    if forbidden:
        raise AssertionError(f"Forbidden payment-risk model features: {sorted(forbidden)}")
    return columns


def _timestamps(values):
    parsed = pd.to_datetime(values, format="mixed", utc=True, errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"Missing or invalid {values.name}")
    return parsed


def _numeric(values):
    parsed = pd.to_numeric(values, errors="coerce")
    if parsed.isna().any() or not np.isfinite(parsed).all():
        raise ValueError(f"Missing or invalid {values.name}")
    return parsed


def _category(values):
    return values.str.strip().str.lower().replace("", "na")


def load_rows(data_dir):
    folder = Path(data_dir)
    columns = feature_columns()
    flags = columns["binary"][1:]
    payments = read_table(folder, "payments.csv", [
        "payment_id", "invoice_id", "team_id", "collected_at", "amount_usd",
        "tip_usd", "receipt_sent", *PAYMENT_CATEGORIES,
    ], "payment_id")
    payments["collected_at"] = _timestamps(payments["collected_at"])
    cohort = {"payment_rows_read": len(payments), "collection_end_exclusive": COLLECTION_END.isoformat()}
    payments = payments.loc[payments["collected_at"] < COLLECTION_END].copy()
    cohort["payments_before_collection_end"] = len(payments)
    cohort["payments_excluded_on_or_after_collection_end"] = (
        cohort["payment_rows_read"] - len(payments)
    )

    invoices = read_table(folder, "invoices.csv", [
        "invoice_id", "team_id", "job_type", "line_item_count", *flags,
    ], "invoice_id").rename(columns={"team_id": "invoice_team_id"})
    frame = payments.merge(invoices, on="invoice_id", how="left", validate="many_to_one", indicator=True)
    matched = frame["_merge"].eq("both")
    cohort["payments_excluded_missing_invoice"] = int((~matched).sum())
    frame = frame.loc[matched].copy()
    if not (frame["team_id"].str.strip().ne("") & frame["team_id"].eq(frame["invoice_team_id"])).all():
        raise ValueError("Matched payment and invoice team IDs must be present and agree")

    amount = _numeric(frame["amount_usd"])
    if not amount.gt(0).all():
        raise ValueError("amount_usd must be positive")
    frame["log_amount_usd"] = np.log(amount)
    frame["tip_usd"] = _numeric(frame["tip_usd"])
    item_count = _numeric(frame["line_item_count"])
    if not (item_count.ge(0) & item_count.mod(1).eq(0)).all():
        raise ValueError("line_item_count must be a nonnegative integer")
    frame["line_item_count"] = item_count
    for column in columns["categorical"]:
        frame[column] = _category(frame[column])
    frame["card_country"] = frame["card_country"].where(frame["card_country"].isin(["us", "na"]), "foreign")
    for column in columns["binary"]:
        frame[column] = boolean_values(frame[column])

    photos = read_table(folder, "photos.csv", ["photo_id", "invoice_id", "kind", "uploaded_at"], "photo_id")
    photos["uploaded_at"] = _timestamps(photos["uploaded_at"])
    if not photos["kind"].isin(["before", "after"]).all():
        raise ValueError("Unexpected photo kind")
    frame = frame.merge(photo_counts(frame, photos), on="payment_id", how="left", validate="one_to_one")

    dispute_ids = pd.read_csv(folder / "disputes.csv", usecols=["payment_id"], dtype=str, keep_default_na=False)
    if dispute_ids["payment_id"].str.strip().eq("").any():
        raise ValueError("Dispute rows require a populated payment_id")
    frame[LABEL] = frame["payment_id"].isin(dispute_ids["payment_id"]).astype(int)
    cohort["payments_eligible"] = len(frame)
    cohort["eligible_payments_with_dispute"] = int(frame[LABEL].sum())
    features = [name for group in columns.values() for name in group]
    return frame[["payment_id", "collected_at", LABEL, *features]].sort_values(
        ["collected_at", "payment_id"]
    ).reset_index(drop=True), cohort
