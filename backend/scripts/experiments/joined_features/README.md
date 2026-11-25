# Cumulative dispute feature comparison

Run from the repository root with the local data path.

```sh
.venv/bin/python backend/scripts/evaluate_disputes.py /path/to/2_data/disputes.csv --joined
```

The script reads source files locally and prints aggregate checks, metrics,
calibration tables, and final-variant coefficients. Corrected runs save
aggregate artifacts to `artifacts/joined_features_corrected/` by default.
The scores here are from the original run, before the signature history correction.

The fixed fold proportions are 50%/25% and 75%/25%. Training outcomes must
close by the cutoff. The run verifies training and test dispute identity before
and after joining. New fold metadata includes one SHA-256 digest of the
sorted test IDs per fold. Historical metadata here keeps the original counts
and cutoff timestamps.
Each variant uses C=1.0 and fits its encoding and scaling on training rows only.
Missing joins or invalid numeric/boolean inputs fail explicitly.

Group A adds payment fields. Group B adds invoice fields. Group C adds
before/after photo counts at each payment's collection time and a team signature
history flag. Group D adds profession and team size.

## Snapshot limitation

Historical invoice values reflect the August 2026 snapshot. Groups B and C
therefore use invoice flags whose actual availability at earlier scoring times
is unknown. The corrected team signature flag means that at least one invoice
from the same team, with a creation timestamp strictly earlier than the
current invoice, shows a completion signature in that snapshot. The current
invoice and all invoices with the same creation timestamp are excluded.
This flag cannot establish when the signature was obtained. Photo counts use
uploaded_at <= collected_at and come from photos.csv.

## Observed comparison

The original v1 had the best mean AUC, log loss, and Brier score among the
evaluated cumulative variants. Its metrics and the lookup baseline reproduced
their prior values. No joined group met the pre-set rule v1 remains the dispute-stage model all variants kept as rejected experiments.
