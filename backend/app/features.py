"""Validate CSV uploads and construct the frozen model inputs."""

import csv
from datetime import datetime, timezone
import io
import math


PAYMENT_COLUMNS = [
    "payment_id", "invoice_id", "team_id", "customer_id", "collected_at", "amount_usd",
    "tip_usd", "payment_method", "card_country", "card_type", "avs_result", "cvv_result", "receipt_sent",
]
INVOICE_COLUMNS = [
    "invoice_id", "team_id", "customer_id", "job_type", "line_item_count",
    "customer_address_present", "signed_estimate", "terms_accepted", "completion_signature",
]
PHOTO_COLUMNS = ["photo_id", "invoice_id", "kind", "uploaded_at"]
DISPUTE_COLUMNS = [
    "dispute_id", "payment_id", "invoice_id", "team_id", "opened_at", "reason", "amount_usd",
    "merchant_responded", "evidence_submitted",
]


def parse_csv(content, columns, name, key, *, skip_blank_keys=False):
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{name} is missing columns: {', '.join(sorted(missing))}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"{name} has duplicate column headers")
        rows = []
        seen = set()
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{name} has malformed CSV rows")
            row = {column: value.strip() for column, value in row.items()}
            identity = row[key]
            if not identity and skip_blank_keys:
                continue
            if not identity or identity in seen:
                raise ValueError(f"{name} requires unique nonempty {key} values")
            seen.add(identity)
            rows.append(row)
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError(f"{name} must be a valid UTF-8 CSV file") from error
    return rows


def number(value, column, *, positive=False):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{column} must be numeric") from error
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{column} must be finite{' and positive' if positive else ''}")
    return result


def boolean(value, column):
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{column} must be true or false")
    return int(normalized == "true")


def timestamp(value, column):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{column} must contain valid dates") from error
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def payment_features(payments, invoices, photos):
    by_invoice = {row["invoice_id"]: row for row in invoices}
    photo_groups = {}
    for photo in photos:
        if photo["invoice_id"] not in by_invoice:
            continue
        if photo["kind"] not in {"before", "after"}:
            raise ValueError("Photo kind must be before or after")
        photo_groups.setdefault(photo["invoice_id"], []).append(
            (photo["kind"], timestamp(photo["uploaded_at"], "uploaded_at"))
        )
    inputs, checklists = [], []
    for payment in payments:
        collected = timestamp(payment["collected_at"], "collected_at")
        amount = number(payment["amount_usd"], "amount_usd", positive=True)
        invoice = by_invoice.get(payment["invoice_id"])
        if invoice is None:
            inputs.append(None)
            checklists.append([
                "Add the missing invoice ID to this payment." if not payment["invoice_id"]
                else "Include the matching invoice in the next upload."
            ])
            continue
        for column in ("team_id", "customer_id"):
            if not payment[column] or payment[column] != invoice[column]:
                raise ValueError(f"Payment and invoice {column} must agree")
        line_items = number(invoice["line_item_count"], "line_item_count")
        if line_items < 0 or not line_items.is_integer():
            raise ValueError("line_item_count must be a nonnegative integer")
        counts = {"before": 0, "after": 0}
        for kind, uploaded in photo_groups.get(invoice["invoice_id"], []):
            counts[kind] += uploaded <= collected
        row = {
            "log_amount_usd": math.log(amount), "log_amount": math.log(amount),
            "tip_usd": number(payment["tip_usd"], "tip_usd"),
            "line_item_count": line_items, "job_type": invoice["job_type"].lower() or "na",
            "photos_before_at_payment": counts["before"], "photos_after_at_payment": counts["after"],
            "receipt_sent": boolean(payment["receipt_sent"], "receipt_sent"),
        }
        for column in ("payment_method", "card_country", "card_type", "avs_result", "cvv_result"):
            row[column] = payment[column].lower() or "na"
        if row["card_country"] not in {"us", "na"}:
            row["card_country"] = "foreign"
        actions = []
        for rule in EVIDENCE_RULES.values():
            action = rule(invoice, row)
            if action:
                actions.append(action)
        inputs.append(row)
        checklists.append(actions)
    return inputs, checklists


def customer_address(invoice, payment):
    if not boolean(invoice["customer_address_present"], "customer_address_present"):
        return "Add the service address to the invoice."


def signed_estimate(invoice, payment):
    if not boolean(invoice["signed_estimate"], "signed_estimate"):
        return "Collect a signed estimate where applicable."


def terms_accepted(invoice, payment):
    if not boolean(invoice["terms_accepted"], "terms_accepted"):
        return "Record the customer's acceptance of the terms."


def completion_signature(invoice, payment):
    if not boolean(invoice["completion_signature"], "completion_signature"):
        return "Request confirmation that the work was completed."


def itemized_invoice(invoice, payment):
    if payment["line_item_count"] == 0:
        return "Add itemized work and material descriptions."


def job_description(invoice, payment):
    if "job_description_chars" in invoice and number(invoice["job_description_chars"], "job_description_chars") < 40:
        return "Add a clearer description of the work performed."


def receipt(invoice, payment):
    if not payment["receipt_sent"]:
        return "Send the customer a payment receipt."


def job_photos(invoice, payment):
    if payment["photos_after_at_payment"] == 0:
        return "Keep dated photos showing the completed work."


EVIDENCE_RULES = {
    "customer_address": customer_address,
    "signed_estimate": signed_estimate,
    "terms_accepted": terms_accepted,
    "completion_signature": completion_signature,
    "itemized_invoice": itemized_invoice,
    "job_description": job_description,
    "receipt": receipt,
    "job_photos": job_photos,
}
