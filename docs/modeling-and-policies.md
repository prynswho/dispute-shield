# Modeling and policy reference

## Mandatory-address what-if

The What-if tab evaluates mandatory customer addresses over months 1–22.
Its inputs are the aggregate SQL results supplied by the user, stored in
`backend/app/policy_data/address_mandatory.json`. Reproduce its reports without
accessing source CSVs.

```sh
.venv/bin/python backend/scripts/evaluate_policies.py
```

Aggregate reports are saved in mode-labelled folders under
`backend/scripts/experiments/policies/`.
The app serves the same calculation through `/api/policies` and exports
`/api/policies/whatif_results.csv`.

The policy uses central attrition of 3% across all jobs with invoice amount under
$300, including jobs already showing an address. Sensitivity cases use 2% and
4%, chosen around the brief's approximate 3%. Disputes and historical losses
decline proportionally with this job attrition. On retained jobs currently
lacking addresses, conservative, central, and optimistic scenarios close
0%, 50%, and 100% of the observed resolved-loss-rate gap within each amount
band. The calculation evaluates all nine independent combinations of attrition
and evidence benefit. The central estimate uses 3% attrition and 50% gap closure.
Retained jobs have unchanged dispute incidence. Avoided losses use the
historical mean lost principal plus the $25 fee within each affected band.
The resolved-only reference gives open and withdrawn disputes zero observed
loss and no evidence-related outcome change. The main analysis adds expected
open outcomes as described below.

The bounds are scenarios. Confidence is low because address timing is
unverified in the historical snapshot and team or job differences may explain
the observed gap. The supplied cohort excludes 52 unmatched payments.
Lost revenue and margin from job attrition are outside the reported dispute
loss savings. Resolved-only central changes are -19.65 disputes, -53.67 disputes
lost, and -$73,674.35 in dollars lost. Across the nine scenarios, changes range
from -26.20 to -13.10 disputes, -99.56 to -7.50 lost disputes, and -$145,682.62
to -$1,608.20 in dollars lost. Fractional counts represent expectations.

Policies use the `POLICIES` function registry in `backend/app/policies.py`.
Add a calculation function and its aggregate input JSON to register another
policy. The generic view and CSV export consume the same report structure.
Checklist actions use `EVIDENCE_RULES` in `backend/app/features.py`.
`REASONS` in `backend/app/catalog.py` supplies the portfolio reason filter.
All three catalogs are available through `/api/catalog`.

## Signed-estimate what-if

`signed_estimate_over_1000` is registered in the same `POLICIES` mapping.
It uses the user's aggregate counts for invoice amounts strictly above
$1,000, including the corrected unsigned duplicate outcome counts.
The affected population is 14,131 unsigned invoices. Zero job attrition,
unchanged dispute incidence, and zero added operating cost are assumed.
The baseline shown in the results table covers the full months 1–22 portfolio.

Resolved loss-rate gaps are calculated within each dispute reason.
The conservative, central, and optimistic scenarios close 0%, 50%, and 100%
of positive observed gaps. Fraud has no positive gap. Duplicate is assigned
zero benefit because only three signed cases resolved. Credit-not-processed
contributes to the scenarios but has only six resolved signed cases, making
its benefit especially uncertain. Avoided losses use unsigned lost principal
per lost dispute plus $25. The resolved-only reference gives open and
withdrawn cases no assumed evidence improvement.

Resolved-only central changes are 0 disputes, -18.40 disputes lost, and -$86,511.49 in
dollars lost. The dollar-change bounds are -$173,022.99 to $0. These scenarios
are low-confidence estimates with observational assumptions.

Historical invoices are August 2026 snapshots. We cannot verify whether
signed estimates were collected before payment or dispute. The observed
win-rate difference may partly reflect later evidence collection or
differences between jobs and teams. This limitation appears in the What-if
view and saved scenario JSON as well as this README.

Both policies are evaluated independently. Do not add their savings without
accounting for jobs and disputes affected by both. Re-running the policy
report command exports six rows, one for each policy and metric.

## Policy outcome sensitivity

The default What-if analysis is `open_expected`. It keeps actual won/lost
outcomes fixed, assigns each open case expected losses of `1 - win_prob`,
and keeps withdrawn cases at zero observed loss. Dollars use that probability
times disputed amount plus $25. The point estimate is an expectation.

Prepare the aggregate sensitivity artifact using the frozen dispute logistic
v1. The script validates the local cohort against the supplied aggregate counts
and reports unscorable cases. It retains aggregate effects without dispute IDs
or row-level predictions.

```sh
.venv/bin/python backend/scripts/prepare_policy_outcomes.py /path/to/2_data
.venv/bin/python backend/scripts/evaluate_policies.py
```

The preparation run scored 175 open and 96 withdrawn cases, with zero
unscorable cases. Output is stored in
`backend/app/policy_data/outcome_sensitivity.json`. Its model digest records
which artifact supplied the probabilities. Regenerate it after changing the
frozen model or approved policy calculations. Stale calculation references
fail explicitly.

The range combines all-won, predicted, and all-lost open treatments with the
existing policy scenarios. Each treatment supplies both the baseline and
counterfactual before calculating their difference. Original dispute counts
are preserved, with attrition alone changing their policy count. The baseline
shown in the main table uses probability-weighted open outcomes.

On eligible unresolved cases, the assumed evidence reduction is the group's
observed resolved-loss-rate gap times the selected benefit fraction. Subtract
it from the case's loss probability and cap the result between zero and one.
Apply address attrition first and the evidence effect to retained cases.
The gaps continue to come from resolved outcomes. Predictions are not used
to relearn the observed comparison groups.

For `signed_estimate_over_1000`, dispute incidence and job attrition are
assumed unchanged. Its dispute-count change remains zero.

The UI also offers `withdrawn_sensitivity`, assigning predicted outcomes to
withdrawn cases in addition to the open-case analysis. This reinterprets
recorded withdrawals. Those probabilities are unvalidated because the model
trained on won and lost outcomes. Open-case probabilities can also suffer
from differences in follow-up and resolution.

Reports for `resolved_only`, `open_expected`, and `withdrawn_sensitivity`
are saved separately under `backend/scripts/experiments/policies/`. The
original top-level reports remain the resolved-only reference. Each CSV keeps
`policy,metric,estimated_change,low,high` and six data rows.
The download and API take the same `mode` query parameter.

With open cases probability weighted, address central changes are -19.65
disputes, -60.35 losses and -$84,074.71. Signed-estimate central changes are
0 disputes, -21.25 losses and -$97,472.47.

### Estimated effort to add another policy

These are engineering estimates, not measured delivery-time improvements.
With agreed aggregates and assumptions, a similar new policy should take
about 1–2 hours for its calculation, input file, tests, documentation, and
verification. Data investigation and agreement on assumptions can add
another 1–3 hours. New data requirements or causal designs can take longer.

The function registry, shared report structure, generic What-if components,
and CSV exporter remove repeated endpoint and view implementation. The
signed-estimate addition required no new API route or policy-specific React
view. Future policies can reuse the same path by adding a registry entry,
aggregate input JSON, and a function returning that report structure.

## Run locally

From the repo root, set up and start the backend.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-runtime.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload
```

The backend health endpoint is at `http://127.0.0.1:8000/health`. Start the frontend in a second terminal.

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

## Prepare and use the scoring dashboard

Create the model and aggregate files from the historical months 1–22 directory.
Run these commands in the same Python environment you use for the backend.

```sh
.venv/bin/python backend/scripts/save_payment_risk.py /path/to/2_data --output-dir artifacts/reproduced/payment_risk
.venv/bin/python backend/scripts/evaluate_early_win.py /path/to/2_data
.venv/bin/python backend/scripts/prepare_scoring.py /path/to/2_data
.venv/bin/python backend/scripts/prepare_policy_outcomes.py /path/to/2_data
```

The risk export command expects a new output directory. If the risk bundle
already exists, use it or generate a new bundle in a separate directory.
The dashboard loads the saved models and tier thresholds from `artifacts/`.
Set `DISPUTE_ARTIFACT_DIR` to use another directory. The API keeps run results
in `data/uploads/` by default. Set `DISPUTE_UPLOAD_DIR` to change that location.
Upload sessions are Git-ignored. The selected frozen models, encoder, tier thresholds, and historical aggregate summary are tracked for deployment reproducibility. Use the Vite URL printed by the dev
server to open the dashboard.
Each CSV can be up to 40 MiB. The three payment upload files can total up to
80 MiB.

1. Upload invoices, photos, and payments. Review the invoice readiness
   checklist, payment win probability, dispute risk, and estimated dollars
   at risk. Download `payment_predictions.csv`.
2. Upload disputes for the payment run. Review the as-submitted win
   probabilities and fight or accept recommendations. Download
   `dispute_predictions.csv`.
3. Use the team view to filter the uploaded payments and disputes, and the
   portfolio view to inspect the historical totals by dispute reason.

Payments with blank or unmatched invoice IDs appear as Unscored. Their
prediction fields are blank in the CSV, which includes every payment.
Correct the invoice link and upload a new run to score those payments.

Observed historical win rates use won and lost cases. Historical dollars lost
are the disputed amounts plus the $25 fee on cases marked lost. Uploaded
disputes appear as pending. The payment exposure estimate multiplies dispute
risk, conditional loss probability, and payment amount plus the $25 fee.
The fight recommendation compares expected recovery with the $15 cost of
fighting, using the evidence and response status supplied in the dispute.

## Scoring approaches

- `backend/scripts/deterministic_baseline.py` implements the smoothed lookup benchmark.
- `backend/scripts/logistic_regression.py` implements the selected dispute logistic v1.
- Shallow histogram boosting is implemented in the comparison runners, `payment_risk.py`, and `early_win.py`; its results are retained with the experiments.
- `backend/scripts/experiments/` holds aggregate experiment reports.

Compare candidates against the deterministic baseline on the same holdout and metric. Keep local input files under `data/` and generated outputs under `artifacts/`.

## Build checks

```sh
.venv/bin/python -m compileall -q backend
npm --prefix frontend run build
```

Run the synthetic upload and export tests.

```sh
.venv/bin/python -m pip install httpx
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p 'test_upload_api.py'
```

## Evaluate the dispute win models

After installing backend requirements, run from the repo root.

```sh
.venv/bin/python backend/scripts/evaluate_disputes.py /path/to/disputes.csv
```

The evaluator filters to won/lost outcomes, sorts by opening time, and uses
50%/25% and 75%/25% expanding folds. Equal opening timestamps stay together.
Training rows must have closed by the first test timestamp. Output includes
per-fold AUC, log loss, Brier score, calibration, capped evidence counts,
fallback counts, and mean, population standard deviation, minimum and maximum
across folds. Undefined AUC values are excluded from summary statistics and
the defined-fold count is shown.

The baseline uses add-one smoothing and a minimum of 20 training rows for
reason/evidence and reason lookups, then falls back to the overall rate.
The constant reference uses the raw eligible training win rate.
Evidence tokens are trimmed, lowercased, deduplicated, and counted up to six.
A lone `none` counts as zero. Evaluation covers recorded won/lost outcomes.

Logistic regression uses reason, capped evidence count, individual evidence
flags, merchant response, and log amount. The pipeline fits encoders and
numeric scaling independently on each fold's training rows. The report includes
the 10 largest coefficients by absolute size for each fold.

Model functions accept lists of row dicts. `fit(rows)` returns a model dict,
and `predict(model, rows)` returns probabilities in input order. Additional
model pairs can be passed to `evaluate(frame, models)`.

## Compare dispute-stage candidates

Run the comparison locally with the disputes, payments, invoices, photos, and
teams CSVs in the same directory.

```sh
.venv/bin/python backend/scripts/compare_dispute_models.py /path/to/2_data/disputes.csv
```

The comparison uses the same expanding folds for the constant and lookup
baselines, logistic v1, four cumulative joined logistic variants, and
histogram gradient boosting with the v1 and full joined features. Logistic v1
without `merchant_responded` measures sensitivity to that feature and is
explanation-only.

A boosting candidate must improve log loss by at least 0.01 relative to
logistic v1 in each fold. If both qualify, the lower mean log loss wins, with
equal means favoring the v1 feature set. Logistic v1 remains selected when
neither boosting candidate qualifies.

Aggregate scores, summary statistics, calibration, fold metadata, and the
selection decision go to `backend/scripts/experiments/model_comparison/`.
Use `--output-dir` with an empty directory for another run. Each fold records
counts, its cutoff timestamp, and one SHA-256 digest of the sorted test IDs
encoded as a UTF-8 JSON array. The signature history feature checks only
strictly earlier invoices from the same team, using snapshot signature flags.

## Test improvements to logistic v1

```sh
.venv/bin/python backend/scripts/improve_dispute_model.py /path/to/2_data/disputes.csv
```

The original outer folds compare logistic v1, logistic with reason × evidence
token flags, and sigmoid-calibrated v1. In each outer training set, the latest
quarter by opening time is the inner validation window. Earlier disputes must
have closed by the inner cutoff. Disputes opened at the cutoff stay together
in validation, whose labels are already available by the outer cutoff.

The interaction model chooses C from 0.1, 0.3, and 1.0 by inner validation
log loss, breaking ties toward smaller C. For sigmoid calibration, a fixed v1
trained on the earlier rows produces decision scores on the inner validation
window. An unpenalized sigmoid learns from those scores and their labels.
Both base models then fit again on the full outer training set. The fixed
sigmoid maps the refitted v1's decision scores on the outer test set.

This experiment reused the boosting comparison's conservative replacement
rule, requiring a log-loss reduction of at least 0.01 in both outer folds.
If both qualify, lower mean log loss wins, with ties favoring calibration.
The run retained and froze logistic v1. The interaction candidate improved
log loss by 0.00132 and 0.01791, and sigmoid calibration increased log loss
in both folds. `backend/scripts/experiments/v1_improvements/` contains the
aggregate scores, inner tuning results, calibration bins, grouped errors by
reason and merchant response, and the selection decision.

## Evaluate payment dispute risk

Run locally with `payments.csv`, `invoices.csv`, `photos.csv`, and `disputes.csv`
in the same directory.

```sh
.venv/bin/python backend/scripts/evaluate_payment_risk.py /path/to/2_data
```

Each eligible row is a payment collected before June 1, 2026 at 00:00 UTC
with a matching invoice. The report counts payments removed at the collection
cutoff and payments removed because the invoice was missing. A payment is
positive if its ID appears in the supplied disputes snapshot, regardless of
outcome. This snapshot target does not establish whether a historical fold
would already have had its training labels or whether every payment had a
complete dispute follow-up period.

The constant reference uses training prevalence. The lookup uses
payment method × AVS with add-one smoothing and a 20-row minimum, then
falls back to payment method with the same minimum, then the global lookup.
Logistic regression uses `C=1` without class weights. Histogram gradient
boosting uses depth 3, learning rate 0.05, 200 iterations, seed 42, and
disabled early stopping. Encoders and logistic numeric scaling are fitted on
each fold's training rows.

Both learned approaches run with and without the seven invoice flags. They
share log payment amount, tip, receipt sent, payment method, AVS/CVV results,
card type, card country grouped as US/foreign/missing, job type, line-item
count, and before/after photo counts. Photos count only if uploaded by the
collection timestamp. The August 2026 invoice snapshot supplies the invoice
flags, job type, and line-item count. Their values at collection cannot be
verified. Invoice status, invoice update time, and snapshot photo totals are
excluded.

The original full candidate comparison uses collection times at the eligible cohort's 50% and 75% row boundaries. The final selected flag-free logistic is evaluated separately with 40%/60%/80% expanding training boundaries, each followed by the next 20% test window. Run `evaluate_payment_risk.py /path/to/2_data --compare-layouts` to reproduce the separately labelled `two_folds/` and `three_folds/` reports; the latter is the final layout. The no-option command remains the original two-fold candidate comparison. Equal timestamps stay together on the later side of a
boundary, and all models use the same folds. The aggregate reports go to
`backend/scripts/experiments/payment_risk/` by default. They include per-fold
AUC, log loss, Brier score, 10-bin calibration, fold prevalence and counts,
one sorted test-ID digest per fold, and across-fold mean, population standard
deviation, minimum and maximum. Undefined AUC values are excluded from
summary statistics. `invoice_flags_delta.csv` shows the paired score change
with flags minus without flags by model and fold, plus its across-fold mean.
Use `--output-dir` to choose another report directory.

Run the synthetic checks without a local dataset.

```sh
PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_payment_risk.py
```

## Evaluate invoice and payment win probability

Run the conditional win-probability comparison from the repo root.

```sh
.venv/bin/python backend/scripts/evaluate_early_win.py /path/to/2_data
```

The runner uses the locked dispute folds and scores only resolved won/lost
disputes. Each stage compares the training win-rate constant, smoothed lookup,
logistic regression, and shallow histogram boosting. The amount bands are
under $100, $100 to under $300, $300 to under $1,000, and $1,000 or more.
Selection requires lower log loss than the constant in both folds and
features available at the stage. The aggregate reports are under
`backend/scripts/experiments/early_win/`.

Invoice candidates use invoice amount and job type from the historical
snapshot. Their timing is unverified. The payment lookup also uses snapshot
job type. Payment logistic and boosting use collection fields and
timestamp-filtered photos. A score estimates probability of winning among
payments that are disputed and resolve as won or lost.

The fitted bundle is saved to `artifacts/early_win.joblib`. Each stage key
contains the selected model dict or `None`, which represents a blank export.
For a fitted payment model, pass normalized payment feature dicts to
`early_win.predict(model, rows)`. Use the natural log of payment amount as
`log_amount`, integer `receipt_sent`, normalized card fields, and before and
after photo counts through collection. The bundle retains the fitted
preprocessing pipeline.

### Invoice readiness decision

Leave `invoice_win_prob` blank. No invoice candidate beat the training
win-rate constant on log loss in both locked folds. The smoothed lookup scored
0.64396 and 0.65190, while the constant scored 0.63385 and 0.65454. Historical
invoice amount and job type come from the August snapshot, and their values at
invoice readiness could not be verified.

At invoice readiness, show an actionable evidence checklist based on the
invoice as it exists then. Flag a missing service address, missing or vague
line items, and a missing signed estimate where applicable. Example guidance
is “Add the service address before sending.” The app shows this checklist after a payment upload. A standalone invoice-only readiness upload is not implemented. The payment-stage logistic score is available after collection and
estimates win probability conditional on a dispute that resolves as won or lost.

Revisit the invoice model if invoice version history, field-level timestamps,
or documented immutability can establish which fields were available when the
invoice became ready. Count a photo only when its upload timestamp is at or
before a verified invoice-ready timestamp. Compare any new candidate on the
same locked folds and require lower log loss than the constant in both.
