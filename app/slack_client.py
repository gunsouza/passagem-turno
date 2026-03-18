import json
import logging
from urllib.parse import quote

from typing import Dict, List, Optional

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


def _build_thread_setup_blocks(previous_pontos: List[dict]) -> List[dict]:
    """Monta os blocks para a mensagem inicial da thread (botão + pontos anteriores)."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Adicione seus pontos à passagem:*"}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "➕ Adicionar ponto", "emoji": True},
                    "action_id": "adicionar_ponto",
                }
            ],
        },
    ]
    if previous_pontos:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Pontos da passagem anterior (clique para manter):*"},
        })
        for i, p in enumerate(previous_pontos):
            user = p.get("user", "?")
            text = p.get("text", "")
            value = json.dumps({"user": user, "text": text})[:3000]
            blocks.append({
                "type": "section",
                "block_id": f"manter_{i}",
                "text": {"type": "mrkdwn", "text": f"• *{user}:* {text}"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Manter", "emoji": True},
                    "action_id": "manter_ponto",
                    "value": value,
                },
            })
    return blocks


def _build_ponto_blocks(user: str, text: str, turnos: List[str]) -> List[dict]:
    """Monta blocks para um ponto com botão Repassar."""
    value = json.dumps({"user": user, "text": text})[:3000]
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{user}:* {text}"},
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Repassar", "emoji": True},
                "action_id": "repassar_ponto",
                "value": value,
            },
        }
    ]


class SlackNotifier:
    def __init__(
        self,
        bot_token: Optional[str],
        default_channel: Optional[str],
        webhook_url: Optional[str] = None,
    ):
        self.bot_token = bot_token
        self.default_channel = default_channel
        self.webhook_url = (webhook_url or "").strip() or None
        self._client = WebClient(token=bot_token) if bot_token else None

    @property
    def is_webhook_configured(self) -> bool:
        """Incoming Webhook: não exige aprovação de app."""
        return bool(self.webhook_url and self.webhook_url.startswith("https://hooks.slack.com/"))

    @property
    def is_bot_configured(self) -> bool:
        """Bot API: exige escopos aprovados (chat:write, im:write, users:read)."""
        return bool(self._client and self.default_channel)

    @property
    def is_configured(self) -> bool:
        return self.is_webhook_configured or self.is_bot_configured

    def send_report(
        self,
        metrics: Dict[str, Dict],
        title: str,
        analyst: Optional[str] = None,
        links: Optional[Dict[str, str]] = None,
        channel: Optional[str] = None,
        subtitle: Optional[str] = None,
        previous_values: Optional[Dict[str, int]] = None,
        jira_base_url: Optional[str] = None,
    ) -> Optional[Dict]:
        """Envia relatório ao canal. Prioridade: webhook (simples) > Bot API (completo).
        Retorna dict com url, channel, ts ou None."""
        if not self.is_configured:
            return None

        text = self.build_report_text(
            metrics=metrics,
            title=title,
            analyst=analyst,
            links=links,
            subtitle=subtitle,
            previous_values=previous_values,
            jira_base_url=jira_base_url,
        )

        # Prioridade: Incoming Webhook (não exige aprovação de app)
        if self.is_webhook_configured:
            ok = self._send_via_webhook(text)
            return {"url": None, "channel": None, "ts": None, "webhook": ok} if ok else None

        # Bot API (para quando tiver aprovação: DM, botões, modais)
        if self.is_bot_configured:
            try:
                resp = self._client.chat_postMessage(
                    channel=channel or self.default_channel,
                    text=text,
                )
                ts = resp.get("ts")
                channel_id = resp.get("channel")
                if not ts or not channel_id:
                    return None
                url = f"https://app.slack.com/client/T00000000/{channel_id}/p{str(ts).replace('.', '')}"
                return {"url": url, "channel": channel_id, "ts": ts}
            except SlackApiError as exc:
                logger.error("Erro ao enviar Slack: %s", exc.response.get("error", str(exc)))
                return None

        return None

    def _send_via_webhook(self, text: str) -> bool:
        """Envia mensagem via Incoming Webhook. Não suporta thread, DM, botões."""
        try:
            r = requests.post(
                self.webhook_url,
                json={"text": text},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if not r.ok:
                logger.error("Webhook Slack falhou: %s %s", r.status_code, r.text[:200])
                return False
            logger.info("Mensagem enviada ao Slack via webhook")
            return True
        except requests.RequestException as exc:
            logger.error("Erro ao enviar webhook Slack: %s", exc)
            return False

    def send_dm(self, user_id: str, text: str) -> bool:
        """Envia DM para um usuário. Requer escopo im:write."""
        if not self._client:
            return False
        try:
            resp = self._client.conversations_open(users=[user_id])
            if not resp.get("ok"):
                logger.warning("Falha ao abrir DM com %s: %s", user_id, resp.get("error"))
                return False
            dm_channel = resp["channel"]["id"]
            self._client.chat_postMessage(channel=dm_channel, text=text)
            return True
        except SlackApiError as exc:
            logger.error("Erro ao enviar DM: %s", exc.response.get("error", str(exc)))
            return False

    def post_to_thread(self, channel: str, thread_ts: str, text: str, blocks: Optional[List] = None) -> bool:
        """Publica mensagem em uma thread existente."""
        if not self._client:
            return False
        try:
            kwargs = {"channel": channel, "thread_ts": thread_ts}
            if blocks:
                kwargs["blocks"] = blocks
                kwargs["text"] = text  # fallback para notificações
            else:
                kwargs["text"] = text
            self._client.chat_postMessage(**kwargs)
            return True
        except SlackApiError as exc:
            logger.error("Erro ao postar na thread: %s", exc.response.get("error", str(exc)))
            return False

    def get_thread_link(self, channel: str, ts: str) -> str:
        """Retorna link permalink para a thread."""
        if not self._client:
            return ""
        try:
            resp = self._client.chat_getPermalink(channel=channel, message_ts=ts)
            if resp.get("ok"):
                return resp.get("permalink", "")
        except SlackApiError:
            pass
        return f"https://app.slack.com/client/T00000000/{channel}/p{str(ts).replace('.', '')}"

    def post_thread_setup(self, channel: str, thread_ts: str, previous_pontos: List[dict]) -> bool:
        """Publica a mensagem com botão e pontos anteriores na thread."""
        blocks = _build_thread_setup_blocks(previous_pontos)
        return self.post_to_thread(channel, thread_ts, "Adicione seus pontos", blocks=blocks)

    def post_ponto_with_repassar(
        self, channel: str, thread_ts: str, user: str, text: str, turnos: List[str]
    ) -> bool:
        """Publica ponto na thread com dropdown Repassar para T1/T2/T3."""
        blocks = _build_ponto_blocks(user, text, turnos)
        return self.post_to_thread(channel, thread_ts, f"{user}: {text}", blocks=blocks)

    def get_user_display_name(self, user_id: str) -> str:
        """Retorna o nome de exibição do usuário. Requer escopo users:read."""
        if not self._client:
            return user_id
        try:
            resp = self._client.users_info(user=user_id)
            if resp.get("ok"):
                user = resp.get("user", {})
                return user.get("real_name") or user.get("name", user_id)
        except SlackApiError:
            pass
        return user_id

    @staticmethod
    def build_report_text(
        metrics: Dict[str, Dict],
        title: str,
        analyst: Optional[str] = None,
        links: Optional[Dict[str, str]] = None,
        subtitle: Optional[str] = None,
        previous_values: Optional[Dict[str, int]] = None,
        jira_base_url: Optional[str] = None,
    ) -> str:
        # Título principal (ex: Passagem de Turno BR)
        header = f"*{title}*"
        if subtitle:
            header += f"\n{subtitle}"
        header += " 🇧🇷"
        lines = [header]

        prev = previous_values or {}
        # Métricas no formato: Nome: valor (↑N vs anterior)
        for key, m in metrics.items():
            name = m.get("name", key)
            value = m.get("value", 0)
            line = f"• {name}: *{value}*"
            if key in prev and prev[key] is not None:
                delta = value - prev[key]
                if delta > 0:
                    line += f" (↑{delta} vs anterior)"
                elif delta < 0:
                    line += f" (↓{abs(delta)} vs anterior)"
            link = m.get("link")
            if not link and jira_base_url and m.get("jql"):
                link = f"{jira_base_url.rstrip('/')}/issues/?jql={quote(m['jql'])}"
            if link:
                line += f" — <{link}|abrir>"
            lines.append(line)

        if links:
            for label, url in links.items():
                lines.append(f"{label}: <{url}|abrir>")

        if analyst:
            lines.append(f"Analista: {analyst}")

        return "\n".join(lines)
