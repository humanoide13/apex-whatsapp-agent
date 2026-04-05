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

# ─── Configuration ───────────────────────────────────────────────
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "apex-capilar-2026")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
PORT = int(os.getenv("PORT", "8000"))
MAX_HISTORY = 20

# ─── System Prompt ───────────────────────────────────────────────
SYSTEM_PROMPT = """Você é a assistente virtual da APEX CAPILAR, uma clínica especializada em tricologia e restauração capilar localizada no Porto, Portugal. Seu nome é APEX Assistant.

SOBRE A CLÍNICA:
- A APEX CAPILAR é dirigida pelo Dr. Khalil, tricologista especializado em restauração capilar
- Especialidades: consultas de tricologia, transplante capilar FUE (Follicular Unit Extraction), transplante capilar DHI (Direct Hair Implantation), tratamentos capilares clínicos (tópicos, orais e injetáveis)
- A consulta de avaliação tricológica inclui análise completa com tricoscopia digital
- Localização: Porto, Portugal
- Website: https://apexcapilar.com
- Telefone/WhatsApp: +351 932 348 037

AGENDAMENTO DE CONSULTAS:
- Online pelo site: https://apexcapilar.com/agendar.html
- Por telefone/WhatsApp: +351 932 348 037
- Sempre que o paciente quiser agendar, forneça diretamente estas opções de forma clara e objetiva

DIRETRIZES DE COMUNICAÇÃO:
- Seja profissional, acolhedor e elegante na comunicação
- Use português europeu (de Portugal, não do Brasil)
- Trate por "você" de forma respeitosa
- Seja conciso e direto — evite textos longos desnecessários
- Não use emojis em excesso — no máximo 1 por mensagem, e apenas quando apropriado
- Não faça múltiplas perguntas de uma vez — seja objetivo
- Quando o paciente quer agendar, forneça logo os meios de agendamento sem fazer triagem prévia desnecessária

REGRAS IMPORTANTES:
- NUNCA faça diagnósticos médicos — encaminhe sempre para uma consulta presencial
- NUNCA forneça valores de cirurgias ou procedimentos — indique que os valores são personalizados e definidos após avaliação presencial
- Pode dar informações gerais sobre os procedimentos (FUE, DHI, tratamentos)
- Pode explicar como funciona o processo de avaliação e tratamento
- Se não souber a resposta, encaminhe para contacto direto com a clínica

TOM DE VOZ:
- Profissional e confiável, como uma rececionista de clínica premium
- Transmita segurança e competência
- Evite linguagem excessivamente casual ou robótica
- Respostas claras, bem estruturadas e elegantes"""

# ─── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("apex-agent")

# ─── In-memory conversation store ────────────────────────────────
conversations: dict[str, list[dict]] = {}

# ─── Lifespan ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 APEX CAPILAR WhatsApp Agent started")
    yield
    log.info("Agent shutting down")

app = FastAPI(title="APEX CAPILAR WhatsApp Agent", lifespan=lifespan)

# ─── Health check ────────────────────────────────────────────────
@app.get("/")
async def health():
    return {
        "status": "online",
        "service": "APEX CAPILAR WhatsApp Agent",
        "timestamp": datetime.utcnow().isoformat(),
    }

# ─── Webhook verification (GET) ─────────────────────────────────
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        log.info("✅ Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    log.warning("❌ Webhook verification failed")
    return Response(content="Forbidden", status_code=403)

# ─── Webhook handler (POST) ─────────────────────────────────────
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

        # Handle text messages only
        if msg_type == "text":
            text = msg["text"]["body"]
            log.info(f"📩 Message from {sender_name} ({sender}): {text}")

            # Get or create conversation history
            if sender not in conversations:
                conversations[sender] = []

            conversations[sender].append({"role": "user", "content": text})

            # Call Claude API
            reply = await call_claude(sender, sender_name)

            # Send reply via WhatsApp
            await send_whatsapp_message(sender, reply)
            log.info(f"📤 Reply to {sender_name}: {reply[:80]}...")
        else:
            log.info(f"📎 Non-text message ({msg_type}) from {sender_name}")
            await send_whatsapp_message(
                sender,
                "De momento apenas consigo processar mensagens de texto. Como posso ajudá-lo?"
            )

    except Exception as e:
        log.error(f"Webhook processing error: {e}")

    return {"status": "ok"}

# ─── Claude API call ─────────────────────────────────────────────
async def call_claude(sender: str, sender_name: str) -> str:
    messages = conversations.get(sender, [])
    system = SYSTEM_PROMPT + f"\n\nO nome do paciente é: {sender_name}"

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

            # Store assistant reply in history
            conversations[sender].append({"role": "assistant", "content": reply})

            return reply

    except Exception as e:
        log.error(f"Claude API error: {e}")
        return (
            "Pedimos desculpa, mas de momento não conseguimos processar o seu pedido. "
            "Por favor, tente novamente ou contacte-nos diretamente pelo telefone +351 932 348 037 "
            "ou através do nosso site apexcapilar.com."
        )

# ─── Send WhatsApp message ───────────────────────────────────────
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

# ─── Run ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
