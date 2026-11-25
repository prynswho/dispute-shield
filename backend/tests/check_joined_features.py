"""Run with PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_joined_features.py."""

import pandas as pd

from joined_features import photo_counts, signature_history
from logistic_regression import GROUPS, feature_columns

payments = pd.DataFrame({
    "payment_id": ["p1", "p2", "p3"],
    "invoice_id": ["i1", "i1", "i2"],
    "collected_at": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-02"], utc=True),
})
photos = pd.DataFrame({
    "invoice_id": ["i1", "i1", "i1"],
    "kind": ["before", "after", "after"],
    "uploaded_at": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"], utc=True),
})
counts = photo_counts(payments, photos).set_index("payment_id")
assert counts.loc["p1"].tolist() == [1, 1]
assert counts.loc["p2"].tolist() == [1, 2]
assert counts.loc["p3"].tolist() == [0, 0]

invoices = pd.DataFrame({
    "team_id": ["a", "a", "a", "a", "b"],
    "created_at": pd.to_datetime(
        ["2025-01-01", "2025-01-02", "2025-01-02", "2025-01-03", "2025-01-03"], utc=True
    ),
    "completion_signature": [0, 1, 0, 0, 0],
})
assert signature_history(invoices).tolist() == [0, 0, 0, 1, 0]
changed_signatures = invoices.copy()
changed_signatures.loc[1, "completion_signature"] = 0
assert signature_history(changed_signatures).tolist() == [0, 0, 0, 0, 0]
assert signature_history(invoices.iloc[::-1]).tolist() == [0, 1, 0, 0, 0]

for forbidden in ("invoice_status", "updated_at"):
    GROUPS["B"]["categorical"].append(forbidden)
    try:
        feature_columns("ABCD")
    except AssertionError:
        pass
    else:
        raise AssertionError("Forbidden feature was accepted")
    finally:
        GROUPS["B"]["categorical"].pop()
print("Photo cutoff, separate payment times, signature history, and forbidden-feature checks passed")
