# Comando /passagem-turno no Slack

Para que os analistas possam enviar a passagem digitando `/passagem-turno` no Slack:

## 1. Configurar o Slash Command

1. Acesse [api.slack.com/apps](https://api.slack.com/apps)
2. Selecione o app **Natis Diario-de-bordo** (ou crie um novo)
3. No menu lateral: **Slash Commands** → **Create New Command**
4. Preencha:
   - **Command:** `/passagem-turno`
   - **Request URL:** `https://SUA-URL-RAILWAY/slack/slash/passagem-turno`
     (ex: `https://passagem-turno-production.up.railway.app/slack/slash/passagem-turno`)
   - **Short Description:** Envia a passagem de turno ao canal
   - **Usage Hint:** (deixe vazio)
5. Salve

## 2. Variáveis no Railway

O endpoint do slash command exige `SLACK_SIGNING_SECRET`. Adicione no Railway:

- **SLACK_SIGNING_SECRET** = valor em **Basic Information** → **Signing Secret** do seu app no Slack

(O webhook continua usando `SLACK_WEBHOOK_URL`; o signing secret é só para validar que a requisição veio do Slack.)

## 3. Instalar o app no workspace

Se o app ainda não estiver instalado: **Install App** → escolha o workspace → autorize.

## 4. Uso

Qualquer pessoa no canal pode digitar:

```
/passagem-turno
```

A passagem será enviada ao canal configurado no webhook.
