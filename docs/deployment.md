# Railway deployment

The repository includes docs, the approach draft, aggregate experiment reports,
and frozen inference artifacts. Raw source CSVs, upload sessions, credentials,
virtual environments, and installed dependencies are excluded from Git.

The Docker image serves the built React frontend and FastAPI from one origin.
It uses the same Python/sklearn versions as the frozen artifacts. It never
trains models. One Uvicorn worker handles requests; the persistent 500 MB volume
is mounted at `/data`, with upload sessions stored in `/data/uploads`.

Install the Railway CLI and authenticate, then link this directory to the
`dispute-shield` project and service. Infrastructure settings live in
`.railway/railway.ts`; install its SDK with `npm ci` from the repository root.
Review `railway config plan`, then apply with `railway config apply --yes`.
Do not apply a plan that detaches the upload volume.

Build and run locally:

```sh
docker build -t dispute-shield:local .
docker run --rm -p 8000:8000 -v dispute-shield-uploads:/data dispute-shield:local
```

Create the deployment context from the repository root:

```sh
python3 tools/package_deployment.py
```

This prints a temporary directory. Deploy that exact directory with the linked
Railway project, using `railway up DIRECTORY --path-as-root --service dispute-shield`.
It excludes docs, experiments, tests, source datasets, sessions, and Git history
before uploading anything to Railway. `.dockerignore` independently excludes
those files from Docker builds. Runtime policy JSON and the aggregate portfolio
summary are included because the application displays them.

Generate a public Railway domain for the service. Verify `/health`, the UI,
synthetic uploads, both prediction exports, portfolio, and all policy modes.
Verify an uploaded synthetic session survives a service restart. Real customer
data is not needed for deployment verification.

The trial stops when its credit or time allowance runs out; this does not
guarantee continuous hosting for the assignment period. The current app uses
unguessable run IDs rather than user accounts; anyone with a run URL can read
that session. Keep real uploads private and review usage in Railway.
