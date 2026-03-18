## Passagem de Turno – Coleta automática do Jira

Serviço leve (FastAPI) que consulta métricas no Jira via JQL e expõe endpoints para consumo por Grafana (datasource JSON) e envio de relatório para Slack.

### Pré-requisitos
- Python 3.11+
- Token de API do Jira Cloud
- (Opcional) Bot do Slack para envio do relatório

### Instalação
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Crie um arquivo `.env` com as variáveis:
```bash
JIRA_BASE_URL=https://mercadolibre.atlassian.net
JIRA_EMAIL=seu.email@empresa.com
JIRA_API_TOKEN=token
REFRESH_MINUTES=5
# Slack – Incoming Webhook (recomendado, não exige aprovação de app)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxxxxxx
# Slack – Bot API (opcional, para DM, botões e modais; exige aprovação de escopos)
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C0AKE752AG4
SLACK_SIGNING_SECRET=xxxx
# Analista para passagem de turno (opcional)
ANALYST_SLACK=@Nunes
```

### Configuração
Edite `app/config.yaml`:

- **metrics**: JQLs para cada status da fila
- **report**: título, subtítulo (ex: "Passagem de Turno T2"), links
- **schedule.times**: horários para envio automático (ex: `["08:00", "23:56"]`)
- **schedule.analyst**: analista padrão (opcional)
- **dm_users**: lista de Slack User IDs para receber DM com link da thread (notificação)

**Modos de envio ao Slack:**

- **Incoming Webhook** (`SLACK_WEBHOOK_URL`): modo simples, não exige aprovação de app. Envia o relatório no canal; analistas respondem manualmente na thread com os pontos.
- **Bot API** (`SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID`): fluxo completo com botões, modais e DM. Requer aprovação dos escopos `chat:write`, `im:write`, `users:read`. Se ambos estiverem configurados, o webhook tem prioridade.

**Fluxo completo (Bot API):**
1. Bot envia a passagem no canal
2. Primeira mensagem na thread: botão "Adicionar ponto" + pontos da passagem anterior (com botão "Manter")
3. Ao clicar "Adicionar ponto": abre modal para escrever o ponto (validação: não vazio, máx 2000 chars)
4. Ao clicar "Manter": replica o ponto e o botão muda para "✓ Mantido"
5. Cada ponto tem botão "Repassar": abre modal para escolher T1/T2/T3 e envia para a próxima passagem daquele turno
6. DM para cada pessoa em `dm_users` com link direto para a thread

**Configurações adicionais:**
- `schedule.timezone`: timezone para os horários (ex: America/Sao_Paulo)
- `schedule.turno_map`: mapeamento horário → turno para repassar (ex: "08:00": "T1")

**Persistência:** Pontos e pendentes são salvos em `app/data/passagem_store.json`

**Escopos no Slack:** `chat:write`, `im:write`, `users:read`

### Executando localmente
```bash
uvicorn app.main:app --reload --port 8000
```

Endpoints:
- `GET /health` – status, timestamp, métricas e `jira_ok` (conexão com Jira)
- `GET /status` – última passagem, erros recentes, próximos horários
- `GET /metrics/history?days=14` – histórico de métricas (snapshots)
- `GET /dashboard` – dashboard web (métricas, status, histórico)
- `GET /metrics` – todas as métricas
- `GET /metrics/{key}` – métrica específica
- `POST /refresh` – atualiza todas as métricas; body opcional `{ "key": "crises" }`
- `POST /slack/passagem-turno` – dispara manualmente (refresh + envia ao Slack)
- `POST /slack/report` – envia relatório para Slack
- `POST /workflow/report` – retorna texto do relatório (pode enviar se `send_to_slack=true`)
- `POST /workflow/report/slack-signed` – igual, com verificação de assinatura do Slack

### Slack Workflow Builder
Use o passo "Send a web request" no Workflow.

- Método: POST
- URL (sem verificação): `http://<host>:8000/workflow/report`
- URL (com assinatura): `http://<host>:8000/workflow/report/slack-signed`
- Headers: `Content-Type: application/json`
- Body (exemplo):
```json
{
  "title": "Cierre de Turno BR",
  "analyst": "@SeuUsuario",
  "send_to_slack": true
}
```
Saída: JSON com `text` (mensagem pronta) e `message_url` (quando enviado ao canal).

### Grafana (JSON API datasource)
1. Instale o plugin "JSON API" no Grafana.
2. Configure a datasource apontando para `http://<host>:8000`.
3. Exemplos de queries:
   - Lista completa: `GET /metrics`
   - Valor único (transformação): `GET /metrics/waiting_for_support` e selecione o campo `value`.

### Testes
```bash
pip install -r requirements-dev.txt
pytest -v
```

### Docker
```bash
docker build -t shift-metrics .
docker run --env-file .env -p 8000:8000 shift-metrics
```

### Deploy em produção (24/7)

O serviço precisa rodar continuamente para enviar a passagem nos horários agendados.

**Guia completo:** veja [DEPLOY.md](DEPLOY.md) para passo a passo em Railway, Render e Fly.io.

**Resumo rápido (Railway):**
1. Push do código no GitHub
2. [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Adicione as variáveis (JIRA_*, SLACK_WEBHOOK_URL)
4. Generate Domain para obter a URL

**Importante:** Prefira Railway ou Render (execução contínua). Em serverless, o APScheduler pode não funcionar.

### Funcionalidades implementadas

- **Retry no Jira** – até 3 tentativas em falhas temporárias (429, 5xx)
- **Histórico de métricas** – snapshots diários em `app/data/metrics_history.json`
- **Comparação com anterior** – relatório mostra ↑N ou ↓N vs. snapshot anterior
- **Link JQL** – cada métrica tem link para o filtro no Jira
- **Métricas opcionais** – use `enabled: false` no config para desativar uma métrica
- **Alertas** – após 3 falhas consecutivas, envia aviso no Slack
- **Validação no startup** – avisa se JIRA_EMAIL ou JIRA_API_TOKEN faltam

### Segurança
- O serviço só lê contagens via JQL (`maxResults=0`).
- Configure as credenciais via variáveis de ambiente. Não commite `.env`.
