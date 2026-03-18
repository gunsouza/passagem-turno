"""Testes do SlackNotifier."""
from app.slack_client import SlackNotifier


def test_build_report_text():
    """build_report_text formata métricas corretamente."""
    metrics = {
        "backlog": {"name": "Backlog", "value": 10, "link": None},
        "waiting": {"name": "Waiting", "value": 3, "link": "https://jira.example.com"},
    }
    text = SlackNotifier.build_report_text(
        metrics=metrics,
        title="Cierre de Turno",
        analyst="@fulano",
        links={"Grafana": "https://grafana.example.com"},
    )

    assert "*Cierre de Turno*" in text
    assert "Backlog" in text and "10" in text
    assert "Waiting" in text and "3" in text
    assert "abrir" in text
    assert "Grafana" in text
    assert "Analista: @fulano" in text


def test_build_report_text_minimal():
    """build_report_text funciona com parâmetros mínimos."""
    text = SlackNotifier.build_report_text(
        metrics={},
        title="Teste",
    )
    assert "*Teste*" in text


def test_is_configured_false():
    """is_configured é False sem token ou canal."""
    notifier = SlackNotifier(bot_token=None, default_channel="C123")
    assert not notifier.is_configured

    notifier2 = SlackNotifier(bot_token="xoxb-xxx", default_channel=None)
    assert not notifier2.is_configured

    notifier3 = SlackNotifier(bot_token=None, default_channel=None)
    assert not notifier3.is_configured


def test_is_configured_true():
    """is_configured é True com token e canal."""
    notifier = SlackNotifier(bot_token="xoxb-xxx", default_channel="C123")
    assert notifier.is_configured
