from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, List, Optional

from .jira_client import JiraClient
from .metrics_history import get_previous_values, save_snapshot

logger = logging.getLogger(__name__)


class MetricsService:
    """Mantém as métricas configuradas e faz refresh periódico via Jira."""

    def __init__(self, jira_client: JiraClient, metrics_config: Dict[str, Dict]):
        self.jira_client = jira_client
        self.metrics_config = metrics_config or {}
        self._store: Dict[str, Dict] = {}
        self._last_updated: Optional[dt.datetime] = None

    @property
    def last_updated_iso(self) -> Optional[str]:
        return self._last_updated.isoformat() if self._last_updated else None

    def refresh_all(self) -> None:
        for key in self.metrics_config.keys():
            cfg = self.metrics_config.get(key, {})
            if cfg.get("enabled", True) is False:
                continue
            try:
                self.refresh_metric(key)
            except Exception as exc:
                logger.warning("Métrica '%s' falhou (JQL inválido?): %s", key, exc)
        self._last_updated = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
        save_snapshot(self.get_all())

    def refresh_metric(self, key: str) -> Optional[Dict]:
        cfg = self.metrics_config.get(key)
        if not cfg:
            return None
        jql = cfg.get("jql")
        if not jql:
            raise ValueError(f"Métrica '{key}' sem JQL configurado")
        total = self.jira_client.search_total(jql)
        entry = {
            "key": key,
            "name": cfg.get("name", key),
            "jql": jql,
            "link": cfg.get("link"),
            "value": total,
        }
        self._store[key] = entry
        return entry

    def get_all(self) -> Dict[str, Dict]:
        return dict(self._store)

    def get_one(self, key: str) -> Optional[Dict]:
        return self._store.get(key)

    def get_previous_values(self) -> Dict[str, int]:
        """Valores do snapshot anterior para comparação."""
        return get_previous_values(list(self._store.keys()))
