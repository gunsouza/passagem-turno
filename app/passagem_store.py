"""Armazena a thread ativa e os pontos da passagem de turno (com persistência em JSON)."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "passagem_store.json"

_active_thread: Optional[dict] = None
_current_pontos: List[dict] = []
_previous_pontos: List[dict] = []
_pending_for_turno: Dict[str, List[dict]] = {}  # T1, T2, T3 -> lista de pontos


def _ensure_data_dir() -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> None:
    """Carrega dados do arquivo JSON."""
    global _previous_pontos, _pending_for_turno
    if not _DATA_FILE.exists():
        return
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _previous_pontos = data.get("previous_pontos", [])
        _pending_for_turno = data.get("pending_for_turno", {})
    except Exception as exc:
        logger.warning("Erro ao carregar passagem_store: %s", exc)


def _save() -> None:
    """Salva dados no arquivo JSON."""
    _ensure_data_dir()
    try:
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"previous_pontos": _previous_pontos, "pending_for_turno": _pending_for_turno},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as exc:
        logger.warning("Erro ao salvar passagem_store: %s", exc)


def set_active_thread(channel: str, ts: str) -> None:
    global _active_thread
    _active_thread = {"channel": channel, "ts": ts}


def get_active_thread() -> Optional[dict]:
    return _active_thread


def add_ponto(user: str, text: str) -> None:
    """Adiciona ponto à passagem atual."""
    global _current_pontos
    _current_pontos.append({"user": user, "text": text})


def add_pending_for_turno(turno: str, user: str, text: str) -> None:
    """Adiciona ponto pendente para um turno (repassar)."""
    global _pending_for_turno
    if turno not in _pending_for_turno:
        _pending_for_turno[turno] = []
    _pending_for_turno[turno].append({"user": user, "text": text})
    _save()


def get_pending_for_turno(turno: str) -> List[dict]:
    return list(_pending_for_turno.get(turno, []))


def clear_pending_for_turno(turno: str) -> None:
    """Limpa pendentes de um turno após incluir na passagem."""
    global _pending_for_turno
    if turno in _pending_for_turno:
        _pending_for_turno[turno] = []
        _save()


def archive_and_clear_pontos(turno: Optional[str] = None) -> List[dict]:
    """Arquiva pontos atuais como 'anterior', inclui pendentes do turno, limpa.
    Retorna lista de pontos para exibir (previous + pending do turno)."""
    global _current_pontos, _previous_pontos, _pending_for_turno
    _previous_pontos = list(_current_pontos)
    _current_pontos = []
    result = list(_previous_pontos)
    if turno:
        pending = _pending_for_turno.get(turno, [])
        result.extend(pending)
        _pending_for_turno[turno] = []
    _save()
    return result


def get_previous_pontos() -> List[dict]:
    return list(_previous_pontos)


def get_current_pontos() -> List[dict]:
    return list(_current_pontos)


# Carrega dados ao importar
_load()
