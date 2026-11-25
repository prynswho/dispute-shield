"""Local joins for dispute features. Reports contain aggregate checks only."""

import pandas as pd

INVOICE_FLAGS = [
    "customer_address_present", "signed_estimate", "terms_accepted",
    "tech_gps_checkin", "completion_signature",
]
PAYMENT_CATEGORIES = ["payment_method", "avs_result", "cvv_result", "card_country", "card_type"]
INVOICE_NUMERIC = ["line_item_count", "job_description_chars"]


def read_table(folder, name, columns, key):
    table = pd.read_csv(folder / name, usecols=columns, dtype=str, keep_default_na=False)
    if table[key].eq("").any() or table[key].duplicated().any():
        raise ValueError(f"{name} requires unique populated keys")
    return table


def boolean_values(values):
    mapped = values.str.strip().str.lower().map({"true": 1, "false": 0})
    if mapped.isna().any():
        raise ValueError(f"Invalid or missing boolean values in {values.name}")
    return mapped.astype(int)


def join_required(left, right, key):
    joined = left.merge(right, on=key, how="left", validate="many_to_one", indicator=True, sort=False)
    missing = int(joined["_merge"].ne("both").sum())
    print(f"Join on {key}: unmatched {missing}, rows {len(joined)}")
    if missing:
        raise ValueError(f"Missing matches on {key}")
    return joined.drop(columns="_merge")


def photo_counts(payments, photos):
    matches = payments[["payment_id", "invoice_id", "collected_at"]].merge(
        photos[["invoice_id", "kind", "uploaded_at"]], on="invoice_id", how="left"
    )
    eligible = matches.loc[matches["uploaded_at"] <= matches["collected_at"]]
    return pd.crosstab(eligible["payment_id"], eligible["kind"]).reindex(
        index=payments["payment_id"], columns=["before", "after"], fill_value=0
    ).fillna(0).astype(int).rename(
        columns={"before": "photos_before_at_payment", "after": "photos_after_at_payment"}
    ).reset_index()


def signature_history(invoices):
    # Snapshot flag availability is unknown, even though creation times are bounded.
    earliest = invoices.loc[invoices["completion_signature"].eq(1)].groupby("team_id")["created_at"].min()
    first_signed = earliest.reindex(invoices["team_id"]).set_axis(invoices.index)
    return first_signed.lt(invoices["created_at"]).astype(int)


def enrich(disputes, folder):
    payments = read_table(folder, "payments.csv", [
        "payment_id", "invoice_id", "team_id", "collected_at", "receipt_sent",
        *PAYMENT_CATEGORIES,
    ], "payment_id")
    invoices = read_table(folder, "invoices.csv", [
        "invoice_id", "team_id", "created_at", "job_type", *INVOICE_FLAGS, *INVOICE_NUMERIC,
    ], "invoice_id")
    photos = read_table(folder, "photos.csv", [
        "photo_id", "invoice_id", "kind", "uploaded_at",
    ], "photo_id")
    teams = read_table(folder, "teams.csv", ["team_id", "profession", "team_size"], "team_id")
    for table, column in [(payments, "collected_at"), (invoices, "created_at"), (photos, "uploaded_at")]:
        table[column] = pd.to_datetime(table[column], format="mixed", errors="coerce", utc=True)
        if table[column].isna().any():
            raise ValueError(f"Invalid or missing {column}")
    if not photos["kind"].isin(["before", "after"]).all():
        raise ValueError("Unexpected photo kind")
    for column in INVOICE_FLAGS:
        invoices[column] = boolean_values(invoices[column])
    payments["receipt_sent"] = boolean_values(payments["receipt_sent"])
    for column in PAYMENT_CATEGORIES:
        payments[column] = payments[column].str.strip().str.lower().replace("", "na")
    payments["card_country"] = payments["card_country"].map(
        lambda value: value if value in {"us", "na"} else "foreign"
    )
    invoices["team_used_completion_signature"] = signature_history(invoices)
    payments = join_required(payments, photo_counts(payments, photos), "payment_id")
    joined = join_required(disputes, payments.rename(columns={
        "invoice_id": "payment_invoice_id", "team_id": "payment_team_id",
    }), "payment_id")
    if not (joined["invoice_id"].eq(joined["payment_invoice_id"]) &
            joined["team_id"].eq(joined["payment_team_id"])).all():
        raise ValueError("Dispute and payment join IDs disagree")
    joined = join_required(joined, invoices.rename(columns={"team_id": "invoice_team_id"}), "invoice_id")
    if not joined["team_id"].eq(joined["invoice_team_id"]).all():
        raise ValueError("Dispute and invoice team IDs disagree")
    joined = join_required(joined, teams, "team_id")
    if joined["dispute_id"].tolist() != disputes["dispute_id"].tolist():
        raise AssertionError("Join changed dispute order or population")
    return joined
