from __future__ import annotations

import os
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[4]


def resolve_project_python(repo_root: Path | None = None, fallback: str | None = None) -> str:
    root = (repo_root or REPO_ROOT).resolve()
    candidates = [
        root / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python",
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return fallback or sys.executable
