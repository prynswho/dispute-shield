"""Create an allowlisted Railway build context; never include source datasets."""

from pathlib import Path
import shutil
import tempfile


def package(root, destination):
    files = ["Dockerfile", ".dockerignore", "backend/requirements-runtime.txt",
             "frontend/package.json", "frontend/package-lock.json",
             "frontend/index.html", "frontend/vite.config.js",
             "artifacts/dispute_win.joblib", "artifacts/early_win.joblib",
             "artifacts/historical_summary.json", "artifacts/payment_risk/model.joblib",
             "artifacts/payment_risk/encoder.joblib", "artifacts/payment_risk/tiers.json"]
    files += [str(path.relative_to(root)) for path in (root / "backend/scripts").glob("*.py")]
    for name in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    for name in ["backend/app", "frontend/src"]:
        shutil.copytree(root / name, destination / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    return destination


if __name__ == "__main__":
    print(package(Path(__file__).resolve().parents[1],
                  Path(tempfile.mkdtemp(prefix="dispute-shield-deploy-"))))
