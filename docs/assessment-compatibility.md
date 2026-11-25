# Assessment compatibility audit

Reviewed on **2026-11-26** against the four-page *Dispute Shield Round 2 Brief*
and the supplied `release_notes.md`. Text addressed directly to coding assistants
was excluded from the requirements. The candidate folder's informal planning
README is not treated as an additional assessment specification.

This review inspected source code, existing aggregate reports, frozen artifact
configuration, and synthetic tests. It did not read source CSVs or rerun training
on them. Passing a build does not establish accuracy on unseen months 23–24.

## Requirement coverage

| Brief requirement | Status | Evidence and qualification |
|---|---|---|
| Two-step upload: invoices/photos/payments, then disputes without outcomes | Implemented | `backend/app/main.py`, `features.py`, upload API tests. Disputes do not require outcome or closed_at. Extra brief-format columns are accepted. |
| About 4 MB per file / 8 MB total | Implemented with higher limits | 40 MiB per file, 80 MiB payment batch, as requested by the user. No full-size 80 MiB production load test was performed. |
| Score every uploaded payment, exact CSV columns | Implemented with explicit abstention | Payment export schema matches the brief. Missing invoice links retain the payment and leave prediction fields blank, with an Unscored status. All invoice-win values are intentionally blank. |
| Score every uploaded dispute, exact CSV columns | Implemented for valid linked rows | Frozen logistic produces win_prob and fight/accept. Duplicate IDs, malformed inputs, and inconsistent joins are rejected. |
| Use months 1–22 models; never retrain on uploads | Implemented | Inference loads checked-in artifacts. Training functions are invoked only by offline scripts. Current audit did not independently re-establish artifact provenance from source datasets. |
| Invoice readiness and what to add now | Partial workflow | Payment review already includes invoice readiness and actionable evidence guidance. There is no standalone invoice-only prepayment upload. Blank invoice probability is explicitly permitted by the export contract and explained by failed validation plus timing uncertainty. |
| Per-payment predictions and actions | Implemented | `PaymentDetail.jsx`, `PredictionTables.jsx`, `features.EVIDENCE_RULES`: address, estimate, terms, completion confirmation, itemization/description, receipt, photos, high-risk review. These are registry rules, not causal model explanations. |
| Dispute moment: can we win, what evidence to submit, worth fighting | Partial | Win probability and economic recommendation exist. A dispute-specific checklist comparing available evidence with evidence_submitted is absent. Payment-level evidence guidance is present and is not counted as missing. |
| Pick a team: payments, disputes, results, main gaps | Implemented with outcome limitation | Team view filters uploaded rows and shows historical win rate/losses and gaps. Uploaded disputes show Pending because Step 2 supplies no outcomes. No teams.csv upload is required by the brief. |
| Across teams: disputes, win rate, dollars lost by reason | Implemented | Historical summary and reason filter. Win rate uses won/(won+lost); dollars lost uses lost principal + $25. Uploaded pending disputes are shown separately. |
| Mandatory-address policy, months 1–22 | Implemented with assumptions | Three metrics, central estimate and bounds. 3% attrition across all under-$300 jobs; 2%/4% sensitivity. Evidence effects use observational gaps by amount band. Team/job confounding remains. |
| At least one additional policy | Implemented | Signed estimates above $1,000; same three metrics and ranges, zero job attrition and unchanged incidence assumed. Keyed-payment blocking is optional, not required once this second policy exists. |
| Policy range, confidence, and explanation | Implemented | UI, reports, and modeling reference label scenario bounds and low confidence. Ranges are not statistical intervals. Open/withdrawn treatments are explicit; policy savings cannot simply be added because populations overlap. |
| Exact whatif_results.csv schema | Implemented | policy, metric, estimated_change, low, high; one row per policy/metric. All three outcome modes keep the same columns. |
| Three approaches per prediction; keep rejected ones | Implemented in saved evidence | Lookup, logistic, shallow boosting for invoice win, payment win, dispute win, and risk, plus constants. Reports and implementations are retained. Risk full-family comparison uses two folds; the final three-fold report compares only logistic and constant. |
| Designed and justified validation | Implemented with limitations | Locked win folds use opening time and closure availability. Risk folds use collected_at and a May 31 eligibility cutoff. Risk snapshot labels do not prove historical fold-time availability. Repeated model selection on the same folds can make results optimistic. |
| Comparison table: score, calibration, explainability, decision | Documented | `experiments/README.md` includes target-specific score tables, selection rationale, and links to calibration bins. Existing per-fold reports contain full metrics and spread. |
| Git history, README run steps, experiments, reproduction scripts | Implemented | Commit history preserved, pinned run path, experiment index and offline evaluation scripts. New evaluation output can be directed outside frozen artifacts. No historical data rerun occurred during this audit. |
| Hosted URL, no login | Verified at deployment | Public Railway URL; successful public synthetic scoring and export checks recorded in deployment.md. Current audit checks endpoint availability again. |
| Application up for at least seven days | Not established | Trial credit/time is finite. Deployment success and restart persistence do not guarantee the required duration. User must confirm sufficient account allowance for the review period. |
| Separate final approach document, 2–3 pages | Outstanding final deliverable | Local draft retained at output/docs/Dispute_Shield_Approach.docx and removed from current Git tracking at the user's request. Final content/page count and delivery are not certified by this audit. The brief does not require this document to be committed. |
| Full as-is AI transcript.md in repository | Missing | No transcript.md is present. A summary or reconstructed chat would not satisfy the as-is requirement. Export all relevant AI histories before submission. |
| No source data uploaded to AI | Respected during this audit | Only brief/release-note text, code, existing aggregate reports, and synthetic fixtures were inspected. Source CSVs were not opened. Data and sessions are excluded from Git and deployment contexts. This audit cannot attest to activity outside this session. |
| State assumptions | Documented with remaining uncertainty | README, modeling/policy reference, model comparison, UI limitations, and deployment document cover current choices. The final approach document must carry the material assumptions too. |
| Add policies/reasons without rewriting the app | Supported | Plain POLICIES, EVIDENCE_RULES, and REASONS registries; generic policy view and exports. A new model category may require a refit; new reasons are accepted by the existing unknown-category encoder. |

## Timing and release-note compatibility

- Photos could be attached after job closure. Model photo counts come from
  photos.csv filtered by uploaded_at <= collected_at; snapshot invoice photo
  counts are excluded. Synthetic checks cover the equality boundary and photos
  uploaded later.
- Completion signatures launched in December 2025 and adoption varied by team.
  The rejected joined feature considers strictly earlier same-team invoices;
  the current invoice and timestamp ties cannot set their own history flag.
  Snapshot signature values still cannot date adoption. Final risk excludes the
  signature flag; invoice checklist gaps should be treated as advice rather
  than proof that a team failed an available requirement.
- Invoice status was backfilled in June 2026. invoice_status and updated_at
  are excluded from learned features, with synthetic forbidden-feature checks.
- The brief says unseen invoice/photo uploads reflect payment time. The runtime
  still applies the photo cutoff. Training risk retains snapshot job_type and
  line_item_count, an accepted but unverified timing assumption. Selected
  payment-win features use payment fields and timestamped photos.
- Merchant response and submitted evidence have no separate availability
  timestamps. Dispute scoring is conditional on their supplied state; opening-time
  validation does not prove those values were known at first notification.

## Current verification

The following passed using made-up data only:

- 19 API/policy/outcome unittest cases and 6 standalone payment-risk unittest
  cases; the joined-feature, model-comparison, and v1-improvement assertion scripts.
- 6 frontend tests; production Vite build; Python compilation; pip dependency check.
- Root infrastructure SDK clean install from lockfile.
- Docker production build, including frozen artifacts, passed again; all runtime
  layers were unchanged. Public health, frontend, catalog, portfolio, and policy
  endpoints returned HTTP 200 during this audit.

The earlier deployment verification also built the Linux Docker image, scored
synthetic payments/disputes on the public service, checked exports and all policy
modes, and verified a synthetic session survived a restart with unchanged scores.
Those results are recorded separately in deployment.md. This review does not
claim load testing at the raised upload limits, future hosting availability,
unseen-month accuracy, or a fresh historical-data reproduction run.

## Remaining work before submission

1. Export the actual full AI histories as transcript.md; do not fabricate it.
2. Finalize and supply the separate 2–3-page approach document with current
   model decisions, policy assumptions, and limits.
3. Decide whether to add dispute-specific evidence submission guidance and a
   standalone invoice-readiness flow, or explicitly disclose these workflow gaps.
4. Confirm the Railway allowance covers at least seven days.
5. Have the user rerun historical reproduction commands locally if a fresh
   data-based confirmation is wanted. Preserve frozen models and fold edges.

Approach-document removal affects the current Git tree. Earlier commits still
contain the draft; history was preserved rather than rewritten or force-pushed.
