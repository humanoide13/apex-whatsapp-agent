"""
APEX CAPILAR — WhatsApp AI Agent
Powered by Claude (Anthropic) + WhatsApp Business Cloud API
"""

import os
import json
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "apex-capilar-2026")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
PORT = int(os.getenv("PORT", "8000"))
MAX_HISTORY = 20

SYSTEM_PROMPT = """Voce e a assistente virtual da APEX CAPILAR — clinica especializada em tricologia e restauracao capilar no Porto, Portugal.

SOBRE A APEX CAPILAR:

A APEX CAPILAR e uma clinica premium dedicada exclusivamente a solucoes avancadas de restauracao capilar. Aliamos tecnologia de ponta a um acompanhamento clinico rigoroso e personalizado.

O Dr. Khalil e o tricologista responsavel pelas consultas e procedimentos de restauracao capilar.

SERVICOS:

- Consulta de Avaliacao Tricologica — analise completa com tricoscopia digital, diagnostico personalizado e plano de tratamento
- Transplante Capilar FUE (Follicular Unit Extraction) — tecnica minimamente invasiva, sem cicatriz linear
- Transplante Capilar DHI (Direct Hair Implantation) — implantacao direta com caneta Choi, maxima precisao e naturalidade
- Protocolos Clinicos — tratamentos topicos, orais e injetaveis, adaptados a cada caso

CONTACTOS:

Website: apexcapilar.com
Agendamento online: apexcapilar.com/agendar.html
Telefone (apenas chamadas): +351 932 348 037
WhatsApp: +351 936 892 039

LOCALIZACAO E HORARIO:

As consultas realizam-se no Centro de Medicina Integrativa Dra. Ana Moreira, no Porto.

Horario de consultas:
  Segundas-feiras — 9h00 as 13h00
  Sabados — 9h00 as 13h00

AGENDAMENTO:

Quando o paciente pretender agendar, apresente as opcoes de forma direta:

  Online: apexcapilar.com/agendar.html
  Telefone: +351 932 348 037

Nao faca triagem nem multiplas perguntas antes de fornecer os meios de agendamento.

REGRAS DE COMUNICACAO:

Tom e estilo:
- Profissional, elegante e acolhedor — como a rececionista de uma clinica de alto nivel
- Conciso e objetivo — cada mensagem deve ser util e bem estruturada
- Portugues europeu (PT-PT)
- Trate por "voce" com respeito
- Nunca use emojis
- Nunca faca diagnosticos medicos — encaminhe para consulta presencial
- Nunca revele valores de cirurgias ou procedimentos — sao personalizados e definidos apos avaliacao presencial
- Nunca faca multiplas perguntas numa so mensagem
- Se nao souber a resposta, encaminhe para contacto direto

Gestao da conversa:
- De as boas-vindas APENAS na primeira mensagem da conversa. Nas mensagens seguintes, responda diretamente ao que o paciente pergunta, sem repetir saudacoes nem apresentacoes.
- Respostas curtas e elegantes — evite paragrafos longos ou listar informacao em excesso
- Responda apenas ao que foi perguntado, de forma focada
- Encerre com uma abertura para continuar ou com indicacao de como agendar

Primeira mensagem (apenas quando o paciente escreve pela primeira vez):
"Bem-vindo a APEX CAPILAR.

Sou a assistente virtual da clinica. Estou aqui para o ajudar com informacoes sobre os nossos servicos e agendamento de consultas.

Como posso ser util?"

Mensagens seguintes:
Responda diretamente, sem repetir boas-vindas. Seja preciso e profissional."""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("apex-agent")

conversations: dict[str, list[dict]] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("APEX CAPILAR WhatsApp Agent started")
    yield
    log.info("Agent shutting down")

app = FastAPI(title="APEX CAPILAR WhatsApp Agent", lifespan=lifespan)

@app.get("/")
async def health():
    return {
        "status": "online",
        "service": "APEX CAPILAR WhatsApp Agent",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        log.info("Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")
    log.warning("Webhook verification failed")
    return Response(content="Forbidden", status_code=403)

@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        contacts = value.get("contacts", [])
        if not messages:
            return {"status": "no messages"}
        msg = messages[0]
        contact = contacts[0] if contacts else {}
        sender = msg.get("from", "unknown")
        sender_name = contact.get("profile", {}).get("name", "Cliente")
        msg_type = msg.get("type", "")
        if msg_type == "text":
            text = msg["text"]["body"]
            log.info(f"Message from {sender_name} ({sender}): {text}")
            if sender not in conversations:
                conversations[sender] = []
            conversations[sender].append({"role": "user", "content": text})
            reply = await call_claude(sender, sender_name)
            await send_whatsapp_message(sender, reply)
            log.info(f"Reply to {sender_name}: {reply[:80]}...")
        else:
            log.info(f"Non-text message ({msg_type}) from {sender_name}")
            await send_whatsapp_message(
                sender,
                "De momento apenas processamos mensagens de texto.\n\nPara falar connosco diretamente, ligue para +351 932 348 037."
            )
    except Exception as e:
        log.error(f"Webhook processing error: {e}")
    return {"status": "ok"}

async def call_claude(sender: str, sender_name: str) -> str:
    messages = conversations.get(sender, [])
    is_first = len(messages) <= 1
    system = SYSTEM_PROMPT + f"\n\nNome do paciente: {sender_name}\nEsta e a primeira mensagem do paciente: {'sim' if is_first else 'nao'}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 500,
                    "system": system,
                    "messages": messages[-MAX_HISTORY:],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["content"][0]["text"]
            conversations[sender].append({"role": "assistant", "content": reply})
            return reply
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return (
            "Pedimos desculpa, mas de momento nao foi possivel processar o seu pedido.\n\n"
            "Por favor, contacte-nos diretamente:\n"
            "Telefone: +351 932 348 037\n"
            "Website: apexcapilar.com"
        )

async def send_whatsapp_message(to: str, text: str):
    url = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
    except Exception as e:
        log.error(f"Failed to send WhatsApp message: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
