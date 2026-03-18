"""Armazena status da última passagem e erros recentes."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
STATUS_FILE = DATA_DIR / "status_store.json"
MAX_ERRORS = 10


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> Dict:
    _ensure_data_dir()
    if not STATUS_FILE.exists():
        return {}
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save(data: Dict) -> None:
    _ensure_data_dir()
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as exc:
        logger.warning("Erro ao salvar status: %s", exc)


def set_last_passagem_success(turno: Optional[str] = None) -> None:
    data = _load()
    data["last_passagem"] = {
        "at": datetime.utcnow().isoformat(),
        "success": True,
        "turno": turno,
    }
    data["consecutive_failures"] = 0
    _save(data)


def set_last_passagem_failure(reason: str) -> None:
    data = _load()
    data["last_passagem"] = {
        "at": datetime.utcnow().isoformat(),
        "success": False,
        "reason": reason,
    }
    data["consecutive_failures"] = data.get("consecutive_failures", 0) + 1
    errors = data.get("recent_errors", [])
    errors.insert(0, {"at": datetime.utcnow().isoformat(), "reason": reason})
    data["recent_errors"] = errors[:MAX_ERRORS]
    _save(data)


def add_jira_failure() -> None:
    data = _load()
    data["jira_failures"] = data.get("jira_failures", 0) + 1
    _save(data)


def get_status() -> Dict:
    return _load()


def get_consecutive_failures() -> int:
    return _load().get("consecutive_failures", 0)
