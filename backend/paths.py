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
PREFERRED_EXTERNAL_VAULT = Path(os.getenv("OPERATOR_VAULT_EXTERNAL", "E:/JarvisVault"))
ALLOW_LOCAL_FALLBACK = os.getenv("OPERATOR_ALLOW_LOCAL_FALLBACK", "false").strip().lower() == "true"


def _env_path(env_key: str, default: Path) -> Path:
    value = os.getenv(env_key, "").strip()
    if value:
        return Path(value)
    return default


LOGS_PATH = _env_path("OPERATOR_LOGS_PATH", DEFAULT_LOGS_PATH)
DB_PATH = _env_path("OPERATOR_DB_PATH", DEFAULT_DATABASE_PATH)
CONFIG_PATH = _env_path("OPERATOR_CONFIG_PATH", DEFAULT_CONFIG_PATH)
MODELS_PATH = _env_path("OPERATOR_MODELS_PATH", DEFAULT_MODELS_PATH)

if PREFERRED_EXTERNAL_VAULT.exists():
    _default_vault = PREFERRED_EXTERNAL_VAULT
elif ALLOW_LOCAL_FALLBACK:
    _default_vault = DEFAULT_VAULT_PATH
else:
    _default_vault = DEFAULT_VAULT_PATH  # Fall back to local vault

# Skills path: use external vault/skills if vault is external, otherwise use local skills/
_default_skills = (_default_vault / "skills") if _default_vault == PREFERRED_EXTERNAL_VAULT and PREFERRED_EXTERNAL_VAULT.exists() else DEFAULT_SKILLS_PATH

SKILLS_PATH = _env_path("OPERATOR_SKILLS_PATH", _default_skills)
VAULT_PATH = _env_path("OPERATOR_VAULT_PATH", _default_vault)
