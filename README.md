# Dispute Shield

Payment risk, conditional dispute-win scoring, evidence checklists, and policy
scenarios for field-service businesses. FastAPI, React/Vite, scikit-learn;
plain functions and dicts, file storage, no database.

[Live app](https://dispute-shield-production-67817c10.up.railway.app) ·
[Model comparisons](experiments/README.md) ·
[Assessment audit](docs/assessment-compatibility.md) ·
[Deployment](docs/deployment.md) ·
[Modeling and policy reference](docs/modeling-and-policies.md)

## Run locally

Use Python **3.14.3** and Node **25.8.1** to match the verified Docker build.
No source datasets or training are needed to run the checked-in frozen models.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-runtime.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload
```

In another terminal:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open the Vite URL. Its proxy forwards `/api` and `/health` to port 8000.
Or run the production frontend and API together at http://127.0.0.1:8000:

```sh
docker build -t dispute-shield:local .
docker run --rm -p 8000:8000 -v dispute-shield-uploads:/data dispute-shield:local
```

## Use the app

1. Upload `invoices.csv`, `photos.csv`, and `payments.csv` together. Review risk,
   conditional win probability, expected loss, and evidence gaps per payment.
2. Upload linked disputes. `outcome` and `closed_at` are not required. Review
   win probability and fight/accept recommendations.
3. Pick a team, inspect historical portfolio results by reason, or select a
   What-if policy. Download payment, dispute, and policy CSV exports.

Input columns follow the brief; extra columns are accepted. Each CSV can be up
to **40 MiB** and the payment batch **80 MiB**. There is no `teams.csv` upload;
the brief requests only the three payment files followed by disputes.
Team selection uses uploaded IDs and historical aggregate IDs.

Every payment remains in the export. Missing invoice links are **Unscored**,
with blank predictions and corrective advice. Valid linked disputes are scored;
malformed input, duplicate IDs, and conflicting joins fail explicitly. Uploads
never fit or update models. Uploaded disputes display Pending because outcomes
are unavailable; historical results are shown separately.

## Frozen decisions

| Output | Decision |
|---|---|
| Invoice win probability | Blank: no candidate beat the constant in both folds, and historical invoice timing is unverified. |
| Payment win probability | Logistic regression, C=1.0, conditional on a disputed payment resolving won/lost. |
| Dispute risk | Logistic C=1.0 without invoice flags; final three-fold evaluation. |
| Dispute win probability | Logistic v1 C=1.0 using reason, evidence, merchant response, and log amount. |

Win folds stay locked: train 50% / test next 25%, then train 75% / test last
25%; training outcomes must close by the cutoff. Risk has its own constant and
final layout: train 40%, 60%, 80%, each testing the next 20%.
Risk thresholds use pooled out-of-fold scores: top 2% high, next 3% medium.
Ties can expand these proportions; fixed thresholds need not preserve them on
future uploads. See the tracked `artifacts/payment_risk/tiers.json`.

Expected loss is `P(dispute) * (1 - payment_win_prob) * (amount_usd + 25)`.
Fight if `win_prob * (dispute_amount_usd + 25) > 15`; otherwise accept. The $25
fee is assumed avoided/refunded on a win. Win models exclude open/withdrawn
outcomes. Policy outcome treatments and their limitations are explicit in the UI.

The `POLICIES` function registry includes mandatory addresses and signed estimates
for invoice amounts strictly above $1,000. Both report dispute counts, losses,
and dollars lost with scenario bounds and low confidence. Address attrition is
3% of jobs under $300, with 2%/4% sensitivity. Signed estimates assume zero job
loss and unchanged dispute incidence. These observational scenarios are not
causal estimates or statistical confidence intervals.

## Repository

| Path | Purpose |
|---|---|
| `backend/app/` | API, scoring, validation, policy registry, aggregate policy inputs |
| `backend/app/connectors/` | File storage boundary |
| `backend/scripts/` | Training, evaluation, and preparation functions |
| `backend/scripts/experiments/` | Aggregate scores, calibration, and rejected variants |
| `backend/tests/` | Synthetic API, policy, feature, and model checks |
| `frontend/src/components/` | Reusable UI components |
| `frontend/src/views/` | Payments, Disputes, Teams, Portfolio, What-if |
| `artifacts/` | Selected frozen models, encoder, tier thresholds, historical summary |
| `experiments/README.md` | Comparison tables and report index |
| `docs/` | Assessment audit, modeling reference, deployment |
| `tools/package_deployment.py` | Allowlisted deployment context |
| `.railway/railway.ts` | Infrastructure settings |

Local sessions use `data/uploads/`; Railway uses persistent `/data/uploads`.
Override with `DISPUTE_UPLOAD_DIR`; override model location with
`DISPUTE_ARTIFACT_DIR`. Source CSVs, sessions, credentials, and installed
dependencies are ignored by Git. Only the selected frozen artifacts are tracked.
Docs and experiments stay in Git but are excluded from deployment. The approach
draft stays local and must be delivered separately.

## Verify without source data

```sh
.venv/bin/python -m pip install httpx==0.28.1
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py' -v
PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_joined_features.py
PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_model_comparison.py
PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_payment_risk.py
PYTHONPATH=backend/scripts .venv/bin/python backend/tests/check_v1_improvements.py
.venv/bin/python -m compileall -q backend tools
npm --prefix frontend test
npm --prefix frontend run build
```

These checks use made-up data. Historical evaluation and artifact regeneration
commands are in the [modeling reference](docs/modeling-and-policies.md); only
run them with authorized local data access. Generate new artifacts separately
so the frozen deployment models remain unchanged.

## Submission status

The app, exports, three model families per target, rejected experiments, and
two policy analyses are implemented. The [assessment audit](docs/assessment-compatibility.md)
records remaining submission items: the full as-is `transcript.md`, a separate
final 2–3-page approach document, and confirmed hosting for at least seven days.
Blank invoice probability and readiness guidance within payment review are
intentional decisions, not an incomplete standalone invoice workflow. A dedicated
dispute-evidence checklist is optional polish. Snapshot
field timing, risk-label follow-up, calibration, and policy confounding remain
limitations. Passing the build does not establish complete assessment compliance.
