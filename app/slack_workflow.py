import json
import logging
from typing import Dict

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.workflows.step.async_step import AsyncWorkflowStep

from .metrics_service import MetricsService
from .passagem_store import add_ponto, add_pending_for_turno, get_active_thread
from .slack_client import SlackNotifier

logger = logging.getLogger(__name__)

MODAL_CALLBACK_ID = "modal_adicionar_ponto"
MODAL_REPASSAR_CALLBACK_ID = "modal_repassar_ponto"
MAX_PONTO_LENGTH = 2000


def create_jira_metrics_step(metrics_service: MetricsService) -> AsyncWorkflowStep:
    async def edit(ack, step, configure):
        await ack()
        # Sem inputs configuráveis por enquanto; só declara outputs
        await configure(blocks=[], private_metadata="")

    async def save(ack, view, update):
        await ack()
        outputs = [
            {"name": "backlog_total", "type": "text", "label": "Backlog Total"},
            {"name": "waiting_for_support", "type": "text", "label": "Waiting for Support"},
            {
                "name": "waiting_for_support_p1p2",
                "type": "text",
                "label": "Waiting for Support (P1/P2)",
            },
        ]
        await update(inputs={}, outputs=outputs)

    async def execute(step, complete, fail, logger):
        try:
            # Atualiza métricas antes de completar o step
            metrics_service.refresh_all()
            metrics: Dict[str, Dict] = metrics_service.get_all()

            def get_value(key: str) -> str:
                entry = metrics.get(key) or {}
                return str(entry.get("value", 0))

            outputs = {
                "backlog_total": get_value("backlog_total"),
                "waiting_for_support": get_value("waiting_for_support"),
                "waiting_for_support_p1p2": get_value("waiting_for_support_p1_p2"),
            }
            await complete(outputs=outputs)
        except Exception as exc:  # pragma: no cover - caminho de erro
            await fail(error={"message": str(exc)})

    return AsyncWorkflowStep(
        callback_id="jira_metrics",
        edit=edit,
        save=save,
        execute=execute,
    )


def init_slack_app(
    bot_token: str,
    signing_secret: str,
    metrics_service: MetricsService,
    slack_notifier: SlackNotifier,
    turnos: list = None,
):
    turnos = turnos or ["T1", "T2", "T3"]
    app = AsyncApp(token=bot_token, signing_secret=signing_secret)
    step = create_jira_metrics_step(metrics_service)
    app.step(step)

    @app.action("adicionar_ponto")
    async def handle_adicionar_ponto(ack, body, client):
        await ack()
        thread = get_active_thread()
        if not thread:
            return
        await client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": MODAL_CALLBACK_ID,
                "title": {"type": "plain_text", "text": "Adicionar ponto"},
                "submit": {"type": "plain_text", "text": "Enviar"},
                "close": {"type": "plain_text", "text": "Cancelar"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "ponto_block",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "ponto_input",
                            "multiline": True,
                            "max_length": MAX_PONTO_LENGTH,
                            "placeholder": {"type": "plain_text", "text": "Descreva o ponto para a passagem..."},
                        },
                        "label": {"type": "plain_text", "text": "Ponto"},
                    }
                ],
            },
        )

    @app.action("manter_ponto")
    async def handle_manter_ponto(ack, body, client):
        thread = get_active_thread()
        if not thread:
            await ack()
            return
        try:
            value = json.loads(body["actions"][0]["value"])
            user = value.get("user", "?")
            text = value.get("text", "")
            reply_text = f"*{user}:* {text} _(repassado da passagem anterior)_"
            if slack_notifier.post_to_thread(thread["channel"], thread["ts"], reply_text):
                add_ponto(user, text)
            msg = body.get("message", {})
            blocks = msg.get("blocks", [])
            for b in blocks:
                if b.get("accessory", {}).get("action_id") == "manter_ponto":
                    b["accessory"] = {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✓ Mantido", "emoji": True},
                        "action_id": "manter_ponto_done",
                        "value": "_",
                        "disabled": True,
                    }
                    break
            await client.chat_update(
                channel=body["channel"]["id"],
                ts=msg["ts"],
                blocks=blocks,
                text=msg.get("text", ""),
            )
        except (json.JSONDecodeError, KeyError):
            pass
        await ack()

    @app.action("repassar_ponto")
    async def handle_repassar_ponto(ack, body, client):
        await ack()
        thread = get_active_thread()
        if not thread:
            return
        try:
            value_str = body["actions"][0].get("value", "{}")
            point_data = json.loads(value_str)
            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": MODAL_REPASSAR_CALLBACK_ID,
                    "title": {"type": "plain_text", "text": "Repassar para turno"},
                    "submit": {"type": "plain_text", "text": "Repassar"},
                    "close": {"type": "plain_text", "text": "Cancelar"},
                    "private_metadata": value_str[:3000],
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "turno_block",
                            "element": {
                                "type": "static_select",
                                "action_id": "turno_select",
                                "placeholder": {"type": "plain_text", "text": "Selecione o turno"},
                                "options": [{"text": {"type": "plain_text", "text": t}, "value": t} for t in turnos],
                            },
                            "label": {"type": "plain_text", "text": "Repassar para"},
                        }
                    ],
                },
            )
        except (json.JSONDecodeError, KeyError):
            pass

    @app.view(MODAL_REPASSAR_CALLBACK_ID)
    async def handle_repassar_modal_submit(ack, body, view, client):
        await ack()
        try:
            values = view.get("state", {}).get("values", {})
            turno_block = values.get("turno_block", {})
            turno_select = turno_block.get("turno_select", {})
            turno = turno_select.get("selected_option", {}).get("value")
            if not turno:
                return
            point_data = json.loads(view.get("private_metadata", "{}"))
            user = point_data.get("user", "?")
            text = point_data.get("text", "")
            add_pending_for_turno(turno, user, text)
        except (json.JSONDecodeError, KeyError):
            pass

    @app.view(MODAL_CALLBACK_ID)
    async def handle_modal_submit(ack, body, view, client):
        values = view.get("state", {}).get("values", {})
        ponto_block = values.get("ponto_block", {})
        ponto_input = ponto_block.get("ponto_input", {})
        text = (ponto_input.get("value") or "").strip()
        if not text:
            await ack(response_action="errors", errors={"ponto_block": "O ponto não pode estar vazio."})
            return
        if len(text) > MAX_PONTO_LENGTH:
            await ack(response_action="errors", errors={"ponto_block": f"Máximo {MAX_PONTO_LENGTH} caracteres."})
            return
        thread = get_active_thread()
        if not thread:
            await ack()
            return
        user_id = body.get("user", {}).get("id")
        user_name = slack_notifier.get_user_display_name(user_id) if user_id else "Anônimo"
        if slack_notifier.post_ponto_with_repassar(
            thread["channel"], thread["ts"], user_name, text, turnos
        ):
            add_ponto(user_name, text)
        await ack()

    handler = AsyncSlackRequestHandler(app)
    return app, handler
