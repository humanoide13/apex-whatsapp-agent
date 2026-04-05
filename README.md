# 🏥 APEX CAPILAR — WhatsApp AI Agent

Assistente virtual inteligente para a clínica APEX CAPILAR, powered by **Claude (Anthropic)** + **WhatsApp Business Cloud API**.

## O que faz

- ✅ Responde perguntas sobre procedimentos (FUE, DHI, tricologia)
- ✅ Faz triagem inicial do paciente (histórico, queixas, expectativas)
- ✅ Encaminha para agendamento de consulta presencial
- ✅ Mantém histórico de conversa por paciente
- ✅ Detecta idioma e responde no idioma do paciente
- ✅ Trata mensagens de áudio e imagem com resposta adequada
- ✅ Nunca faz diagnósticos nem informa valores cirúrgicos

---

## Setup Rápido

### 1. Pré-requisitos

- Python 3.11+
- Conta no [Meta for Developers](https://developers.facebook.com)
- API Key da [Anthropic](https://console.anthropic.com)

### 2. Configurar WhatsApp Business API

1. Vá a [developers.facebook.com](https://developers.facebook.com) e crie um App do tipo **Business**
2. Adicione o produto **WhatsApp**
3. Em **API Setup**, copie:
   - **Temporary Access Token** (ou crie um permanente via System User)
   - **Phone Number ID**
4. Em **Webhooks**, configure:
   - **Callback URL**: `https://SEU_DOMINIO/webhook`
   - **Verify Token**: `apex-capilar-2026` (ou o que definir no .env)
   - **Subscribed Fields**: marque `messages`

### 3. Instalar e Rodar

```bash
# Clonar / copiar o projeto
cd apex-whatsapp-agent

# Criar .env a partir do template
cp .env.example .env
# Editar .env com os seus tokens

# Instalar dependências
pip install -r requirements.txt

# Rodar localmente
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Expor para a Internet (desenvolvimento)

Para testes locais, use [ngrok](https://ngrok.com):

```bash
ngrok http 8000
```

Use o URL do ngrok (ex: `https://abc123.ngrok.io/webhook`) como Callback URL no Meta.

### 5. Deploy em Produção

**Opção A — Docker:**
```bash
docker build -t apex-whatsapp-agent .
docker run -p 8000:8000 --env-file .env apex-whatsapp-agent
```

**Opção B — Railway / Render:**
- Faça push para o GitHub
- Conecte ao Railway ou Render
- Adicione as variáveis de ambiente do .env
- O serviço detecta automaticamente o Dockerfile

---

## Estrutura do Projeto

```
apex-whatsapp-agent/
├── app.py              ← Aplicação principal (FastAPI)
├── requirements.txt    ← Dependências Python
├── .env.example        ← Template de variáveis de ambiente
├── Dockerfile          ← Container para deploy
└── README.md           ← Este ficheiro
```

## Arquitetura

```
[Paciente] → WhatsApp → [Meta Cloud API] → POST /webhook → [FastAPI Server]
                                                                │
                                                          Claude API (Anthropic)
                                                                │
                                                          Resposta ← ← ← ←
                                                                │
[Paciente] ← WhatsApp ← [Meta Cloud API] ← POST /messages ← ─┘
```

---

## Próximos Passos (sugestões)

- [ ] **Redis** para persistir conversas entre restarts
- [ ] **Transcrição de áudio** (Whisper API) para aceitar notas de voz
- [ ] **Agendamento real** integrado com Google Calendar
- [ ] **Templates de mensagem** aprovados pelo Meta para mensagens proativas
- [ ] **Dashboard** web para ver conversas e métricas
- [ ] **Rate limiting** para evitar abuso

---

## Licença

Projeto interno — APEX CAPILAR © 2026
