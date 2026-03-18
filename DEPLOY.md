# Deploy 24/7 – Passagem de Turno

Guia para rodar o serviço em nuvem, sem depender do seu computador.

---

## Opção 0: GitHub Actions (100% gratuito, sem servidor)

Roda a passagem de turno nos horários 23:50, 08:00 e 16:00 (America/Sao_Paulo) diretamente pelo GitHub. Não precisa de servidor 24/7.

1. **Configurar secrets** no repositório:
   - GitHub → seu repo → **Settings** → **Secrets and variables** → **Actions**
   - **New repository secret** para cada um:
     - `JIRA_BASE_URL` = `https://mercadolibre.atlassian.net`
     - `JIRA_EMAIL` = seu email
     - `JIRA_API_TOKEN` = token do Jira
     - `SLACK_WEBHOOK_URL` = URL do Incoming Webhook
     - `ANALYST_SLACK` (opcional) = ex: "Automatismo"

2. **Push do código** – o workflow `.github/workflows/passagem-turno.yml` já está pronto.

3. **Pronto.** O workflow roda nos horários:
   - 23:50 BRT
   - 08:00 BRT
   - 16:00 BRT

4. **Disparo manual:** GitHub → **Actions** → **Passagem de Turno** → **Run workflow**.

---

## Pré-requisitos (para Railway/Render/Fly.io)

1. **Repositório no GitHub** – faça push do código:
   ```bash
   git init
   git add .
   git commit -m "Deploy passagem de turno"
   git remote add origin https://github.com/SEU_USUARIO/passagem-turno.git
   git push -u origin main
   ```

2. **Variáveis de ambiente** – você vai precisar:
   - `JIRA_BASE_URL`
   - `JIRA_EMAIL`
   - `JIRA_API_TOKEN`
   - `SLACK_WEBHOOK_URL`
   - `REFRESH_MINUTES` (opcional, padrão: 5)

---

## Opção 1: Railway (recomendado – mais simples)

1. Acesse [railway.app](https://railway.app) e faça login (GitHub).
2. **New Project** → **Deploy from GitHub repo**.
3. Selecione o repositório `passagem-turno`.
4. O Railway detecta o Dockerfile e faz o deploy.
5. Em **Variables**, adicione:
   - `JIRA_BASE_URL` = `https://mercadolibre.atlassian.net`
   - `JIRA_EMAIL` = seu email
   - `JIRA_API_TOKEN` = token do Jira
   - `SLACK_WEBHOOK_URL` = URL do webhook
6. Em **Settings** → **Networking** → **Generate Domain** para obter a URL pública.
7. A URL será algo como `https://passagem-turno-xxx.up.railway.app`.

**Plano gratuito:** ~500 horas/mês. Suficiente para rodar 24/7.

---

## Opção 2: Render

1. Acesse [render.com](https://render.com) e faça login (GitHub).
2. **New** → **Web Service**.
3. Conecte o repositório.
4. **Build Command:** (deixe vazio – usa Docker)
5. **Dockerfile path:** `./Dockerfile`
6. Em **Environment**, adicione as variáveis (JIRA_*, SLACK_WEBHOOK_URL).
7. **Create Web Service**.

**Plano gratuito:** o serviço “dorme” após 15 min de inatividade. Para 24/7, use plano pago ou considere Railway.

---

## Opção 3: Fly.io

1. Instale o [flyctl](https://fly.io/docs/hands-on/install-flyctl/).
2. `fly auth login`
3. No diretório do projeto:
   ```bash
   fly launch --no-deploy
   ```
4. Configure as variáveis:
   ```bash
   fly secrets set JIRA_BASE_URL="https://mercadolibre.atlassian.net"
   fly secrets set JIRA_EMAIL="seu@email.com"
   fly secrets set JIRA_API_TOKEN="seu_token"
   fly secrets set SLACK_WEBHOOK_URL="https://hooks.slack.com/..."
   ```
5. `fly deploy`

---

## Após o deploy

- **Health:** `https://SUA-URL/health`
- **Dashboard:** `https://SUA-URL/dashboard`
- **Passagem manual:** `POST https://SUA-URL/slack/passagem-turno`

O agendamento (23:50, 08:00, 16:00) usa o timezone `America/Sao_Paulo` configurado no `config.yaml`.

---

## Observação sobre dados

Os arquivos em `app/data/` (histórico, status, pontos) são **efêmeros** em containers. Se o serviço reiniciar, esses dados podem ser perdidos. Para persistência, use volumes (Railway/Render) ou um banco de dados externo.
