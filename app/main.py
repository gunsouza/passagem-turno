import logging
import os
import pathlib
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import yaml

from .jira_client import JiraClient
from .metrics_service import MetricsService
from .passagem_store import (
    archive_and_clear_pontos,
    get_active_thread,
    set_active_thread,
)
from .slack_client import SlackNotifier
from .slack_workflow import init_slack_app
from .security import verify_slack_signature
from .metrics_history import get_history
from .status_store import (
    get_status,
    get_consecutive_failures,
    set_last_passagem_failure,
    set_last_passagem_success,
)


class RefreshRequest(BaseModel):
    key: Optional[str] = None


class SlackReportRequest(BaseModel):
    title: Optional[str] = None
    analyst: Optional[str] = None
    links: Optional[Dict[str, str]] = None


class WorkflowReportRequest(BaseModel):
    title: Optional[str] = None
    analyst: Optional[str] = None
    links: Optional[Dict[str, str]] = None
    send_to_slack: bool = False  # quando true, envia ao canal; sempre retorna o texto


def _project_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def load_config() -> Dict:
    config_path = _project_root() / "app" / "config.yaml"
    if not config_path.exists():
        raise RuntimeError(f"Arquivo de configuração não encontrado em {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Carrega .env do diretório do projeto (funciona mesmo rodando de outro diretório)
load_dotenv(_project_root() / ".env")
config = load_config()

# Validação mínima: Jira obrigatório para métricas
def _validate_env() -> list[str]:
    errors = []
    jira_url = os.getenv("JIRA_BASE_URL", config.get("jira", {}).get("base_url"))
    jira_email = os.getenv(config.get("jira", {}).get("email_env", "JIRA_EMAIL"))
    jira_token = os.getenv(config.get("jira", {}).get("api_token_env", "JIRA_API_TOKEN"))
    if not jira_url:
        errors.append("JIRA_BASE_URL não configurado")
    if not jira_email:
        errors.append("JIRA_EMAIL não configurado")
    if not jira_token:
        errors.append("JIRA_API_TOKEN não configurado")
    return errors

jira_base_url = os.getenv("JIRA_BASE_URL", config.get("jira", {}).get("base_url"))
jira_email = os.getenv(config.get("jira", {}).get("email_env", "JIRA_EMAIL"))
jira_api_token = os.getenv(
    config.get("jira", {}).get("api_token_env", "JIRA_API_TOKEN")
)

jira_client = JiraClient(base_url=jira_base_url, email=jira_email, api_token=jira_api_token)
metrics_service = MetricsService(jira_client=jira_client, metrics_config=config.get("metrics", {}))

slack_notifier = SlackNotifier(
    bot_token=os.getenv("SLACK_BOT_TOKEN"),
    default_channel=os.getenv("SLACK_CHANNEL_ID"),
    webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
)

app = FastAPI(title="Shift Handover Metrics API", version="1.0.0")


logger = logging.getLogger(__name__)


ALERT_FAILURE_THRESHOLD = 3  # alertar após N falhas consecutivas


def _run_passagem_turno(turno: Optional[str] = None) -> Optional[Dict]:
    """Atualiza métricas e envia passagem ao canal.

    - Webhook (SLACK_WEBHOOK_URL): envia só o relatório. Analistas respondem manualmente na thread.
    - Bot API (SLACK_BOT_TOKEN + SLACK_CHANNEL_ID): fluxo completo com botões, modais, DM.
    turno: T1, T2 ou T3 (para incluir pontos repassados, só no modo Bot)."""
    try:
        metrics_service.refresh_all()
    except Exception as exc:
        logger.warning("Jira indisponível ao atualizar métricas: %s", exc)
    if not slack_notifier.is_configured:
        set_last_passagem_failure("Slack não configurado")
        return None

    report_cfg = config.get("report", {})
    analyst = os.getenv("ANALYST_SLACK") or config.get("schedule", {}).get("analyst") or None
    metrics = metrics_service.get_all()
    previous = metrics_service.get_previous_values()
    jira_url = config.get("jira", {}).get("base_url") or jira_base_url

    result = slack_notifier.send_report(
        metrics=metrics,
        title=report_cfg.get("title", "Passagem de Turno BR"),
        subtitle=report_cfg.get("subtitle"),
        analyst=analyst,
        links=report_cfg.get("links", {}),
        previous_values=previous,
        jira_base_url=jira_url,
    )
    if not result:
        set_last_passagem_failure("Falha ao enviar ao Slack")
        failures = get_consecutive_failures()
        if failures >= ALERT_FAILURE_THRESHOLD and slack_notifier.is_webhook_configured:
            alert_msg = f"⚠️ *Alerta Passagem de Turno*: {failures} falhas consecutivas ao enviar. Verifique o serviço."
            slack_notifier._send_via_webhook(alert_msg)
        return None

    set_last_passagem_success(turno)

    # Modo webhook: só envia o relatório (sem thread, DM, botões)
    if result.get("webhook"):
        return {"status": "ok", "webhook": True}

    # Modo Bot API: fluxo completo (thread, botões, DM)
    pontos_anteriores = archive_and_clear_pontos(turno)
    set_active_thread(result["channel"], result["ts"])
    thread_link = slack_notifier.get_thread_link(result["channel"], result["ts"])
    slack_notifier.post_thread_setup(
        result["channel"], result["ts"], pontos_anteriores
    )
    dm_msg = (
        f"Olá! :wave:\n\n"
        f"A passagem de turno foi publicada. "
        f"<{thread_link}|Clique aqui para adicionar seus pontos>."
    )
    for user_id in config.get("dm_users") or []:
        if user_id.strip():
            slack_notifier.send_dm(user_id.strip(), dm_msg)
    return result


@app.on_event("startup")
def startup_event() -> None:
    env_errors = _validate_env()
    if env_errors:
        logger.warning("Variáveis de ambiente faltando: %s. Métricas do Jira não funcionarão.", env_errors)
    try:
        metrics_service.refresh_all()
    except Exception as exc:
        logger.warning("Jira indisponível no startup (app inicia com métricas vazias): %s", exc)
    scheduler = BackgroundScheduler(daemon=True)
    interval_minutes = int(os.getenv("REFRESH_MINUTES", "5"))
    scheduler.add_job(metrics_service.refresh_all, "interval", minutes=interval_minutes)

    # Passagem de turno em horários específicos (com timezone)
    schedule_cfg = config.get("schedule", {})
    schedule_times = schedule_cfg.get("times", [])
    tz_str = schedule_cfg.get("timezone", "America/Sao_Paulo")
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    turno_map = schedule_cfg.get("turno_map") or {}
    for time_str in schedule_times:
        try:
            hour, minute = map(int, time_str.split(":"))
            turno = turno_map.get(time_str)
            scheduler.add_job(
                lambda t=turno: _run_passagem_turno(t),
                CronTrigger(hour=hour, minute=minute, timezone=tz),
            )
        except (ValueError, AttributeError):
            pass

    scheduler.start()

    # Inicializa Slack app (se credenciais presentes)
    if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_SIGNING_SECRET"):
        global slack_request_handler  # exposto para rota FastAPI
        turnos = list(set((config.get("schedule", {}).get("turno_map") or {}).values()))
        if not turnos:
            turnos = ["T1", "T2", "T3"]
        _, slack_request_handler = init_slack_app(
            bot_token=os.getenv("SLACK_BOT_TOKEN"),
            signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
            metrics_service=metrics_service,
            slack_notifier=slack_notifier,
            turnos=sorted(turnos),
        )


@app.get("/health")
def health() -> Dict:
    jira_ok = jira_client.check_connection() if jira_client.is_configured else False
    return {
        "status": "ok",
        "last_updated": metrics_service.last_updated_iso,
        "metrics_count": len(metrics_service.get_all()),
        "jira_ok": jira_ok,
    }


@app.get("/status")
def status() -> Dict:
    """Status detalhado: última passagem, erros, próximos horários."""
    status_data = get_status()
    schedule_cfg = config.get("schedule", {})
    times = schedule_cfg.get("times", [])
    return {
        "last_passagem": status_data.get("last_passagem"),
        "recent_errors": status_data.get("recent_errors", [])[:5],
        "consecutive_failures": status_data.get("consecutive_failures", 0),
        "next_schedule": times,
        "timezone": schedule_cfg.get("timezone", "America/Sao_Paulo"),
    }


@app.get("/metrics")
def get_metrics() -> Dict[str, Dict]:
    return metrics_service.get_all()


@app.get("/metrics/history")
def get_metrics_history(days: int = 30) -> Dict:
    """Histórico de métricas (snapshots dos últimos N dias)."""
    if days < 1 or days > 90:
        return {"snapshots": [], "error": "days deve ser entre 1 e 90"}
    snapshots = get_history(days=days)
    return {"snapshots": snapshots, "days": days}


@app.get("/metrics/{key}")
def get_metric(key: str) -> Dict:
    metric = metrics_service.get_one(key)
    if not metric:
        raise HTTPException(status_code=404, detail=f"Métrica '{key}' não encontrada")
    return metric


@app.post("/refresh")
def refresh(req: Optional[RefreshRequest] = Body(default=None)) -> Dict:
    if req is None:
        req = RefreshRequest()
    if req.key:
        updated = metrics_service.refresh_metric(req.key)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Métrica '{req.key}' não encontrada")
    else:
        metrics_service.refresh_all()
    return {"status": "ok", "last_updated": metrics_service.last_updated_iso}


@app.post("/slack/passagem-turno")
def trigger_passagem_turno() -> Dict:
    """Dispara manualmente a passagem de turno (refresh + envio ao Slack)."""
    if not slack_notifier.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Slack não configurado. Defina SLACK_WEBHOOK_URL ou SLACK_BOT_TOKEN+SLACK_CHANNEL_ID no .env",
        )
    result = _run_passagem_turno()
    if result:
        msg = "Passagem de turno enviada"
        url = result.get("url") if isinstance(result, dict) else None
        return {"status": "ok", "message": msg, "message_url": url}
    raise HTTPException(
        status_code=502,
        detail="Falha ao enviar ao Slack. Verifique a configuração (webhook ou token/canal).",
    )


@app.post("/slack/report")
def send_slack_report(req: SlackReportRequest) -> Dict:
    if not slack_notifier.is_configured:
        raise HTTPException(status_code=400, detail="Slack não configurado (defina SLACK_WEBHOOK_URL ou SLACK_BOT_TOKEN+SLACK_CHANNEL_ID)")
    report_cfg = config.get("report", {})
    metrics = metrics_service.get_all()
    result = slack_notifier.send_report(
        metrics=metrics,
        title=req.title or report_cfg.get("title", "Passagem de Turno BR"),
        subtitle=report_cfg.get("subtitle"),
        analyst=req.analyst,
        links=req.links or report_cfg.get("links", {}),
        previous_values=metrics_service.get_previous_values(),
        jira_base_url=config.get("jira", {}).get("base_url") or jira_base_url,
    )
    return {"status": "ok", "message_url": result["url"] if result else None}


@app.post("/workflow/report")
def workflow_report(req: WorkflowReportRequest) -> Dict:
    """Endpoint para Slack Workflow Builder.

    - Sempre retorna o texto do relatório em `text`.
    - Se `send_to_slack = true` e Slack estiver configurado, também publica no canal.
    """
    report_cfg = config.get("report", {})
    title = req.title or report_cfg.get("title", "Passagem de Turno BR")
    metrics = metrics_service.get_all()
    jira_url = config.get("jira", {}).get("base_url") or jira_base_url
    text = slack_notifier.build_report_text(
        metrics=metrics,
        title=title,
        analyst=req.analyst,
        links=req.links or report_cfg.get("links", {}),
        subtitle=report_cfg.get("subtitle"),
        previous_values=metrics_service.get_previous_values(),
        jira_base_url=jira_url,
    )

    message_url = None
    if req.send_to_slack and slack_notifier.is_configured:
        result = slack_notifier.send_report(
            metrics=metrics,
            title=title,
            analyst=req.analyst,
            links=req.links or report_cfg.get("links", {}),
            subtitle=report_cfg.get("subtitle"),
            previous_values=metrics_service.get_previous_values(),
            jira_base_url=jira_url,
        )
        message_url = result["url"] if result else None

    return {"status": "ok", "text": text, "message_url": message_url}


@app.post("/workflow/report/slack-signed")
async def workflow_report_slack_signed(request: Request) -> Dict:
    """Versão do endpoint que valida a assinatura do Slack.

    Configure `SLACK_SIGNING_SECRET` no ambiente e use este endpoint como URL no passo
    "Send a web request" do Workflow Builder.
    """
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    if not signing_secret:
        raise HTTPException(status_code=500, detail="SLACK_SIGNING_SECRET não configurado")

    raw_body = await request.body()
    if not verify_slack_signature(signing_secret, request.headers, raw_body):
        raise HTTPException(status_code=401, detail="Assinatura do Slack inválida")

    payload = await request.json()
    req = WorkflowReportRequest(**payload)

    report_cfg = config.get("report", {})
    title = req.title or report_cfg.get("title", "Passagem de Turno BR")
    metrics = metrics_service.get_all()
    jira_url = config.get("jira", {}).get("base_url") or jira_base_url
    text = slack_notifier.build_report_text(
        metrics=metrics,
        title=title,
        analyst=req.analyst,
        links=req.links or report_cfg.get("links", {}),
        subtitle=report_cfg.get("subtitle"),
        previous_values=metrics_service.get_previous_values(),
        jira_base_url=jira_url,
    )

    message_url = None
    if req.send_to_slack and slack_notifier.is_configured:
        result = slack_notifier.send_report(
            metrics=metrics,
            title=title,
            analyst=req.analyst,
            links=req.links or report_cfg.get("links", {}),
            subtitle=report_cfg.get("subtitle"),
            previous_values=metrics_service.get_previous_values(),
            jira_base_url=jira_url,
        )
        message_url = result["url"] if result else None

    return {"status": "ok", "text": text, "message_url": message_url}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Dashboard web: métricas, status e histórico."""
    dashboard_path = pathlib.Path(__file__).resolve().parent / "static" / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard não encontrado")
    return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))


@app.post("/slack/events")
async def slack_events(request: Request):
    handler = globals().get("slack_request_handler")
    if not handler:
        raise HTTPException(status_code=503, detail="Slack app não inicializado")
    return await handler.handle(request)
