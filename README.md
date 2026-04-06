# APEX CAPILAR — WhatsApp AI Agent

Assistente virtual da APEX CAPILAR via WhatsApp Business Cloud API + Claude (Anthropic).

## Funcionalidades

- Resposta automática via Claude com contexto de conversa persistente
- Logging de todas as conversas (SQLite)
- Dashboard web para consulta de conversas (`/dashboard`)
- API JSON para integração (`/api/conversations`)
- Autenticação por token no dashboard e API

## Variáveis de Ambiente (Railway)

| Variável | Descrição |
|---|---|
| `WHATSAPP_TOKEN` | System User Token (Meta Business) |
| `WHATSAPP_PHONE_ID` | Phone Number ID do número registado |
| `VERIFY_TOKEN` | Token de verificação do webhook |
| `ANTHROPIC_API_KEY` | API key Anthropic |
| `CLAUDE_MODEL` | Modelo Claude (default: `claude-sonnet-4-20250514`) |
| `DASHBOARD_TOKEN` | Token secreto para aceder ao dashboard e API |
| `DB_PATH` | Caminho da base de dados (default: `/data/conversations.db`) |

## Endpoints

| Método | Path | Descrição |
|---|---|---|
| GET | `/` | Health check |
| GET/POST | `/webhook` | WhatsApp webhook |
| GET | `/dashboard?token=XXX` | Dashboard de conversas (HTML) |
| GET | `/api/conversations?token=XXX` | Lista de conversas (JSON) |
| GET | `/api/conversations/{phone}?token=XXX` | Mensagens de um contacto (JSON) |

## Deploy no Railway

1. Conecta o repo GitHub
2. Configura as variáveis de ambiente
3. **Importante:** adiciona um Volume no Railway montado em `/data` para persistir o SQLite
4. Faz deploy

## Migração para número real (+351 936 892 039)

1. **Meta Business Suite** → WhatsApp Manager → Add Phone Number → verificar +351936892039
2. Copiar o novo **Phone Number ID** para `WHATSAPP_PHONE_ID` no Railway
3. Verificar que o System User Token tem permissão para o novo número
4. Gerar um `DASHBOARD_TOKEN` seguro e guardar no Railway
5. Redeploy
