"""Project-local environment loading for Python service entrypoints.

Docker Compose injects `.env` through `env_file`, but local npm scripts like
`npm run telegram` execute Python directly. Loading the project `.env` here
keeps local and Docker behavior aligned without ever printing secret values.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_env(path: Path | str | None = None, *, override: bool = False) -> bool:
    env_path = Path(path) if path is not None else PROJECT_ROOT / ".env"
    if not env_path.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_fallback(env_path, override=override)
    else:
        load_dotenv(env_path, override=override)
    return True


def _load_env_fallback(path: Path, *, override: bool) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
