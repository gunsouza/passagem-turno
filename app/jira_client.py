from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _session_with_retry(retries: int = 3, backoff: float = 0.5) -> requests.Session:
    """Sessão com retry automático para falhas temporárias."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class JiraClient:
    """Cliente mínimo para Jira Cloud usando REST API v3.

    Utiliza autenticação básica (email + token de API). Focado em buscas via JQL
    retornando apenas o total de issues, para evitar transferir payloads grandes.
    """

    def __init__(self, base_url: str, email: Optional[str], api_token: Optional[str]):
        if not base_url:
            raise ValueError("'base_url' do Jira é obrigatório")
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self._session = _session_with_retry()

    @property
    def is_configured(self) -> bool:
        return bool(self.email and self.api_token)

    def search_total(self, jql: str) -> int:
        """Retorna o total de issues que satisfazem o JQL.

        Usa o endpoint /rest/api/3/search/approximate-count (o antigo /search
        foi descontinuado e retorna 410 Gone).
        """
        if not self.is_configured:
            raise RuntimeError("Credenciais do Jira não configuradas (email e token)")

        url = f"{self.base_url}/rest/api/3/search/approximate-count"
        response = self._session.post(
            url,
            json={"jql": jql},
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return int(data.get("count", 0))

    def check_connection(self) -> bool:
        """Verifica se a conexão com o Jira está ok (query simples)."""
        if not self.is_configured:
            return False
        try:
            self.search_total('project = "IS"')
            return True
        except Exception:
            return False
