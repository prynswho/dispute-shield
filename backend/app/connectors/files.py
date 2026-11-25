"""File-backed upload sessions with atomic replacement."""

import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def artifact_dir():
    return Path(os.environ.get("DISPUTE_ARTIFACT_DIR", ROOT / "artifacts"))


def session_path(run_id):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Invalid upload ID")
    folder = Path(os.environ.get("DISPUTE_UPLOAD_DIR", ROOT / "data" / "uploads"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{run_id}.json"


def save_session(session):
    path = session_path(session["run_id"])
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(session, stream, allow_nan=False)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_session(run_id):
    return json.loads(session_path(run_id).read_text())


def portfolio():
    path = artifact_dir() / "historical_summary.json"
    return json.loads(path.read_text()) if path.exists() else {"reasons": [], "teams": []}
