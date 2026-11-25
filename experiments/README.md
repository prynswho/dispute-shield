# Model comparisons and rejected experiments

These tables summarize existing aggregate reports; no source datasets were read
for this documentation update. Fold layouts are kept in separate tables. Lower
log loss and Brier are better; higher AUC is better. Values are unweighted fold
means. Brier measures overall probability error, not calibration alone; the
linked calibration CSVs contain fixed-bin counts, mean predictions, and observed
rates. Full per-fold scores and population standard deviation/min/max remain in
the report folders.

## Dispute win — locked two folds

| Approach | Mean AUC | Mean log loss | Mean Brier |
|---|---:|---:|---:|
| constant | 0.500000 | 0.644196 | 0.225779 |
| baseline | 0.714724 | 0.568177 | 0.196097 |
| v1 | 0.780935 | 0.517605 | 0.176277 |
| hgb_v1 | 0.763069 | 0.529579 | 0.180840 |
| hgb_v1+A+B+C+D | 0.744439 | 0.548088 | 0.188866 |

[Per-fold scores](../backend/scripts/experiments/model_comparison/scores.csv) · [Calibration bins](../backend/scripts/experiments/model_comparison/calibration.csv)

## Invoice win — locked two folds

| Approach | Mean AUC | Mean log loss | Mean Brier |
|---|---:|---:|---:|
| constant | 0.500000 | 0.644196 | 0.225779 |
| lookup | 0.509791 | 0.647930 | 0.227062 |
| logistic | 0.517189 | 0.651386 | 0.228228 |
| boosting | 0.481787 | 0.671608 | 0.236117 |

[Per-fold scores](../backend/scripts/experiments/early_win/invoice/scores.csv) · [Calibration bins](../backend/scripts/experiments/early_win/invoice/calibration.csv)

## Payment win — locked two folds

| Approach | Mean AUC | Mean log loss | Mean Brier |
|---|---:|---:|---:|
| constant | 0.500000 | 0.644196 | 0.225779 |
| lookup | 0.509791 | 0.647930 | 0.227062 |
| logistic | 0.587624 | 0.632557 | 0.219602 |
| boosting | 0.561692 | 0.655171 | 0.228460 |

[Per-fold scores](../backend/scripts/experiments/early_win/payment/scores.csv) · [Calibration bins](../backend/scripts/experiments/early_win/payment/calibration.csv)

## Risk candidate comparison — original two folds

| Approach | Mean AUC | Mean log loss | Mean Brier |
|---|---:|---:|---:|
| constant | 0.500000 | 0.046708 | 0.007953 |
| lookup | 0.762945 | 0.040006 | 0.007604 |
| logistic_without_flags | 0.801520 | 0.036357 | 0.006951 |
| hgb_without_flags | 0.804472 | 0.036100 | 0.006961 |

[Per-fold scores](../backend/scripts/experiments/payment_risk/scores.csv) · [Calibration bins](../backend/scripts/experiments/payment_risk/calibration.csv)

## Final risk layout — three folds

| Approach | Mean AUC | Mean log loss | Mean Brier |
|---|---:|---:|---:|
| constant | 0.500000 | 0.046667 | 0.007946 |
| logistic_without_flags | 0.801676 | 0.036435 | 0.006948 |

[Per-fold scores](../backend/scripts/experiments/payment_risk/three_folds/scores.csv) · [Calibration bins](../backend/scripts/experiments/payment_risk/three_folds/calibration.csv)

## Interpretation and selection

| Approach | Explainability | Decision and probability assessment |
|---|---|---|
| Constant | One training prevalence/win rate | Reference in every fold; supplies no ranking. |
| Smoothed lookup | Explicit segment counts and fallback rates | Tried for every target; retained as a benchmark. Invoice lookup fails to beat the constant in both folds. |
| Logistic regression | Linear coefficients after train-only encoding/scaling | Dispute v1 remains selected. Payment logistic beats the constant on log loss in both folds, with modest ranking performance. Invoice logistic does not qualify. Flag-free risk logistic was chosen for simplicity and fewer unverified invoice fields. Inspect calibration bins before interpreting any individual probability as well calibrated. |
| Shallow histogram boosting | Less transparent nonlinear splits | Dispute boosting fails the pre-set 0.01 improvement in both folds. Invoice/payment boosting fails the constant comparison rule. Risk boosting slightly improves mean log loss in the original two-fold comparison; the final decision still favors the user-selected flag-free logistic for explainability. Boosting has not been evaluated on the final three-fold layout, so no three-fold superiority claim is made. |

Dispute v1 uses C=1.0, reason, capped evidence count, individual evidence flags,
merchant response, and log amount. No `none` evidence column is created. Joined
A/B/C/D variants, response ablation, interactions, and sigmoid calibration are
retained with their selection decisions. No joined group met the pre-set rule;
v1 remains the dispute-stage model and all joined variants are rejected experiments.
The response ablation is explanation-only. Interactions improve mean loss but
miss the required 0.01 gain in each fold; calibration worsens the saved comparison.

Invoice probability remains blank. All three invoice approaches were tried;
none beat the constant in both locked folds, and snapshot timing is unverified.
An invoice checklist is shown within payment review, as agreed. A separate
invoice-only upload is not required and would not resolve the snapshot timing
limitation.

The risk model removes `customer_address_present`, `customer_email_present`,
`customer_phone_present`, `signed_estimate`, `terms_accepted`, `tech_gps_checkin`,
and `completion_signature`. Job type and line-item count remain snapshot fields
with an explicit limitation. Risk labels use a full disputes snapshot, so the
expanding split does not itself prove fold-time label availability. Eligibility
ends before June 1, 2026 UTC to reduce delayed-dispute censoring.

## Final risk detail

[Three-fold scores](../backend/scripts/experiments/payment_risk/three_folds/scores.csv)
include PR-AUC as average precision, relative log-loss gain against the constant,
and top-1/2/5% capture counts and rates. Mean AUC is 0.801676, mean log loss
0.036435, and mean Brier 0.006948. Log-loss gains over the constant are 23.64%,
20.29%, and 21.87% by fold. The top 2% captures 40.33%, 35.83%, and 39.70% of
observed disputes. Fixed-bin calibration and prevalence are preserved in the same
folder. These aggregate historical results do not establish unseen-month accuracy.

## Report index

| Folder | Contents and status |
|---|---|
| [model_comparison](../backend/scripts/experiments/model_comparison/) | Authoritative corrected dispute comparison: constant, lookup, v1, cumulative joined variants, boosting, response ablation. |
| [joined_features](../backend/scripts/experiments/joined_features/) | Original joined experiment before the signature-history correction; kept for history, superseded by model_comparison. |
| [v1_improvements](../backend/scripts/experiments/v1_improvements/) | Rejected interactions and sigmoid calibration; inner tuning and grouped errors. |
| [payment_risk](../backend/scripts/experiments/payment_risk/) | Original two-fold full family/flag comparison at the folder root. |
| [payment_risk/two_folds](../backend/scripts/experiments/payment_risk/two_folds/) | Focused constant versus flag-free logistic, two folds. |
| [payment_risk/three_folds](../backend/scripts/experiments/payment_risk/three_folds/) | Final selected risk layout, focused constant versus flag-free logistic. |
| [early_win/invoice](../backend/scripts/experiments/early_win/invoice/) | Three rejected families plus constant; blank export decision. |
| [early_win/payment](../backend/scripts/experiments/early_win/payment/) | Three families plus constant; selected logistic. |
| [policies](../backend/scripts/experiments/policies/) | Aggregate scenarios and exact-schema exports, separated by outcome treatment. |

## Reproduce with authorized local source data

These commands read the supplied data directory. They were **not** run during
this assessment audit. Output goes to a fresh directory rather than replacing
frozen artifacts or the checked-in experiment evidence.

```sh
.venv/bin/python backend/scripts/compare_dispute_models.py /path/to/2_data/disputes.csv --output-dir artifacts/review/dispute
.venv/bin/python backend/scripts/improve_dispute_model.py /path/to/2_data/disputes.csv --output-dir artifacts/review/improvements
.venv/bin/python backend/scripts/evaluate_payment_risk.py /path/to/2_data --output-dir artifacts/review/risk_candidates
.venv/bin/python backend/scripts/evaluate_payment_risk.py /path/to/2_data --compare-layouts --output-dir artifacts/review/risk_layouts
.venv/bin/python backend/scripts/evaluate_early_win.py /path/to/2_data --output-dir artifacts/review/early_win --model-path artifacts/review/early_win.joblib
```

All estimators use plain fit/predict functions. See the modeling reference for
fold cutoff rules, label definitions, photo timing, and final bundle preparation.
