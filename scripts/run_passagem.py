#!/usr/bin/env python3
"""Script standalone para rodar a passagem de turno (usado pelo GitHub Actions)."""

import os
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
import requests

# Importa após ajustar o path
from app.jira_client import JiraClient
from app.slack_client import SlackNotifier


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config_path = root / "app" / "config.yaml"
    if not config_path.exists():
        print("ERROR: config.yaml não encontrado")
        return 1

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    jira = config.get("jira", {})
    base_url = os.getenv("JIRA_BASE_URL", jira.get("base_url", ""))
    email = os.getenv(jira.get("email_env", "JIRA_EMAIL"), "")
    token = os.getenv(jira.get("api_token_env", "JIRA_API_TOKEN"), "")
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")

    if not (base_url and email and token):
        print("ERROR: JIRA_BASE_URL, JIRA_EMAIL e JIRA_API_TOKEN são obrigatórios")
        return 1

    if not webhook or not webhook.startswith("https://hooks.slack.com/"):
        print("ERROR: SLACK_WEBHOOK_URL é obrigatório")
        return 1

    jira_client = JiraClient(base_url=base_url, email=email, api_token=token)
    metrics_config = config.get("metrics", {})

    metrics = {}
    for key, cfg in metrics_config.items():
        if cfg.get("enabled", True) is False:
            continue
        jql = cfg.get("jql")
        if not jql:
            continue
        try:
            total = jira_client.search_total(jql)
            metrics[key] = {
                "key": key,
                "name": cfg.get("name", key),
                "value": total,
                "jql": jql,
            }
            print(f"  {cfg.get('name', key)}: {total}")
        except Exception as e:
            import traceback
            print(f"WARNING: Métrica '{key}' falhou: {e}")
            traceback.print_exc()

    if not metrics:
        print("ERROR: Nenhuma métrica obtida. Verifique JIRA_* e permissões do token.")

    report = config.get("report", {})
    analyst = os.getenv("ANALYST_SLACK") or config.get("schedule", {}).get("analyst", "")
    text = SlackNotifier.build_report_text(
        metrics=metrics,
        title=report.get("title", "Passagem de Turno BR"),
        subtitle=report.get("subtitle"),
        analyst=analyst or None,
        links=report.get("links", {}),
        jira_base_url=base_url,
    )
    if not metrics:
        text += "\n\n⚠️ _Não foi possível obter métricas. Verifique logs do GitHub Actions._"

    r = requests.post(
        webhook,
        json={"text": text},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    if not r.ok:
        print(f"ERROR: Slack webhook falhou: {r.status_code} {r.text[:200]}")
        return 1

    print("OK: Passagem enviada ao Slack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
