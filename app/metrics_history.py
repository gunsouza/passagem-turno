"""Histórico de métricas (snapshots diários) para comparação e tendências."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
HISTORY_FILE = DATA_DIR / "metrics_history.json"
MAX_DAYS = 30  # manter últimos 30 dias


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_history() -> List[Dict]:
    """Carrega histórico do arquivo."""
    _ensure_data_dir()
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("snapshots", [])
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Erro ao carregar histórico: %s", exc)
        return []


def _save_history(snapshots: List[Dict]) -> None:
    """Salva histórico no arquivo."""
    _ensure_data_dir()
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"snapshots": snapshots, "updated": datetime.utcnow().isoformat()}, f, indent=2)
    except IOError as exc:
        logger.warning("Erro ao salvar histórico: %s", exc)


def save_snapshot(metrics: Dict[str, Dict]) -> None:
    """Salva snapshot das métricas (um por dia)."""
    today = date.today().isoformat()
    values = {k: m.get("value", 0) for k, m in metrics.items()}
    snapshots = _load_history()

    # Substituir ou adicionar snapshot de hoje
    snapshots = [s for s in snapshots if s.get("date") != today]
    snapshots.append({"date": today, "values": values})
    snapshots.sort(key=lambda s: s["date"], reverse=True)

    # Manter apenas MAX_DAYS
    snapshots = snapshots[:MAX_DAYS]
    _save_history(snapshots)


def get_history(days: int = 30) -> List[Dict]:
    """Retorna snapshots dos últimos N dias (ordenados do mais recente ao mais antigo)."""
    snapshots = _load_history()
    if not snapshots:
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [s for s in snapshots if s.get("date", "") >= cutoff]


def get_previous_values(metrics_keys: List[str]) -> Dict[str, int]:
    """Retorna valores do snapshot anterior (ontem ou último disponível)."""
    snapshots = _load_history()
    if not snapshots:
        return {}
    today = date.today()
    for s in snapshots:
        d = s.get("date", "")
        try:
            snap_date = datetime.strptime(d, "%Y-%m-%d").date()
            if snap_date < today:
                return {k: s.get("values", {}).get(k, 0) for k in metrics_keys}
        except (ValueError, TypeError):
            continue
    return {}
