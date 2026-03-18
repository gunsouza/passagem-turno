# Deploy no Railway – Passo a passo

## 1. Criar conta e projeto

1. Acesse [railway.app](https://railway.app) e faça login com GitHub.
2. Clique em **New Project**.
3. Escolha **Deploy from GitHub repo**.
4. Selecione o repositório `passagem-turno` (ou `gunsouza/passagem-turno`).
5. Se pedir, autorize o Railway a acessar o repositório.

## 2. Configurar variáveis

No projeto, clique no serviço criado → **Variables** → **Add Variable** (ou **RAW Editor** para colar várias):

| Variável | Valor |
|----------|-------|
| `JIRA_BASE_URL` | `https://mercadolibre.atlassian.net` |
| `JIRA_EMAIL` | seu email do Jira |
| `JIRA_API_TOKEN` | token de API do Jira |
| `SLACK_WEBHOOK_URL` | URL do Incoming Webhook |
| `ANALYST_SLACK` | `Automatismo` (opcional) |
| `SLACK_SIGNING_SECRET` | Para comando `/passagem-turno` no Slack (veja SLACK_COMANDO.md) |

## 3. Gerar domínio público

1. Clique no serviço → **Settings** → **Networking**.
2. Em **Public Networking**, clique em **Generate Domain**.
3. A URL será algo como `https://passagem-turno-production-xxxx.up.railway.app`.

## 4. Aguardar o deploy

O Railway detecta o `Dockerfile` e faz o build automaticamente. Aguarde alguns minutos.

## 5. Testar

- **Health:** `https://SUA-URL/health`
- **Dashboard:** `https://SUA-URL/dashboard`
- **Passagem manual:** `POST https://SUA-URL/slack/passagem-turno` (body vazio ou `{}`)

Para testar via curl:
```bash
curl -X POST https://SUA-URL/slack/passagem-turno
```

## Horários automáticos

O agendamento roda nos horários **23:50**, **08:00** e **16:00** (America/Sao_Paulo). Não é necessário fazer nada além do deploy.

## Plano gratuito

~500 horas/mês. Um serviço 24/7 usa ~720h, então pode estourar. Para teste contínuo, considere o plano pago ou desligar o serviço quando não precisar.
