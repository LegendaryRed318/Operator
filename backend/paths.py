#!/usr/bin/env python3
"""
paths.py - Centralized path resolution for Operator backend modules.
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_LOGS_PATH = REPO_ROOT / "logs"
DEFAULT_DATABASE_PATH = REPO_ROOT / "database" / "errors.db"
DEFAULT_CONFIG_PATH = BACKEND_DIR / "config.json"
DEFAULT_MODELS_PATH = REPO_ROOT / "models"
DEFAULT_SKILLS_PATH = REPO_ROOT / "skills"
DEFAULT_VAULT_PATH = REPO_ROOT / "vault"


def _env_path(env_key: str, default: Path) -> Path:
    value = os.getenv(env_key, "").strip()
    if value:
        return Path(value)
    return default


LOGS_PATH = _env_path("OPERATOR_LOGS_PATH", DEFAULT_LOGS_PATH)
DB_PATH = _env_path("OPERATOR_DB_PATH", DEFAULT_DATABASE_PATH)
CONFIG_PATH = _env_path("OPERATOR_CONFIG_PATH", DEFAULT_CONFIG_PATH)
MODELS_PATH = _env_path("OPERATOR_MODELS_PATH", DEFAULT_MODELS_PATH)
SKILLS_PATH = _env_path("OPERATOR_SKILLS_PATH", DEFAULT_SKILLS_PATH)
VAULT_PATH = _env_path("OPERATOR_VAULT_PATH", DEFAULT_VAULT_PATH)
