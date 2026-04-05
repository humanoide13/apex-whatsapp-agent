"""
APEX CAPILAR — WhatsApp AI Agent
Powered by Claude (Anthropic) + Meta WhatsApp Business Cloud API
"""

import os
import json
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from contextlib import asynccontextmanager

# ─── Config ───────────────────────────────────────────────────────────────────

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")           # Meta access token
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")     # Phone number ID
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "apex-capilar-2026")  # Webhook verify
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_HISTORY = 20  # messages to keep per conversation

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("apex-agent")

# ─── In-memory conversation store ────────────────────────────────────────────
# In production, swap this for Redis / a database
conversations: dict[str, list[dict]] = {}

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é a **Assistente Virtual da APEX CAPILAR**, uma clínica de restauração capilar localizada em São Félix da Marinha, Porto, Portugal.

## Sobre a Clínica
- **Especialidade**: Tricologia clínica e restauração capilar cirúrgica
- **Técnicas cirúrgicas**: FUE (Follicular Unit Extraction) e DHI (Direct Hair Implantation)
- **Tratamentos complementares**: Protocolos tópicos, orais e injetáveis (mesoterapia, PRP, etc.)
- **Consultas**: Avaliação tricológica completa com tricoscopia digital
- **Responsável técnico**: Dr. Khalil — Tricologista

## Suas Responsabilidades
1. **Acolher** o paciente de forma empática e profissional
2. **Informar** sobre os serviços, técnicas e o processo de consulta
3. **Triagem inicial**: Fazer perguntas básicas para entender a situação do paciente:
   - Há quanto tempo nota a queda/rarefação?
   - Tem histórico familiar de calvície?
   - Já realizou algum tratamento anterior?
   - Qual a sua principal preocupação/expectativa?
4. **Encaminhar** para agendamento de consulta presencial quando apropriado
5. **Esclarecer dúvidas** frequentes sobre procedimentos, recuperação e expectativas

## Regras de Conduta
- Nunca faça diagnósticos. Diga sempre que a avaliação clínica presencial é necessária.
- Nunca informe valores de procedimentos cirúrgicos — diga que os valores dependem da avaliação individual e serão apresentados na consulta.
- Para consultas de avaliação, pode informar que existe uma taxa de consulta (o paciente pode perguntar o valor na receção).
- Seja acolhedor, objetivo e use linguagem acessível (evite jargão técnico excessivo).
- Responda em **português** por padrão. Se o paciente escrever em outro idioma, responda nesse idioma.
- Mantenha respostas concisas — o WhatsApp é um canal de mensagens curtas.
- Use emojis com moderação (máximo 1-2 por mensagem).
- Se o paciente demonstrar urgência ou angústia, seja especialmente empático.

## FAQ Rápido
- **FUE vs DHI**: Ambas são técnicas minimamente invasivas. FUE extrai folículos individualmente; DHI implanta com caneta Choi sem necessidade de incisões prévias. A melhor técnica depende de cada caso.
- **Recuperação**: Geralmente 7-10 dias para atividades normais; resultado final visível entre 9-12 meses.
- **Dor**: Procedimento feito sob anestesia local; desconforto mínimo.
- **Resultados**: Naturais e definitivos, pois utiliza cabelo do próprio paciente.

## Formato de Resposta
Responda de forma direta e natural, como uma mensagem de WhatsApp. Não use markdown pesado (sem headers #, sem bold excessivo). Pode usar *itálico* e quebras de linha para organizar."""


# ─── FastAPI App ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 APEX CAPILAR WhatsApp Agent started")
    yield
    logger.info("Agent shutting down")

app = FastAPI(title="APEX CAPILAR WhatsApp Agent", lifespan=lifespan)


# ─── Webhook Verification (GET) ──────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta sends a GET request to verify the webhook URL."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("❌ Webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


# ─── Webhook Messages (POST) ─────────────────────────────────────────────────

@app.post("/webhook")
async def receive_message(request: Request):
    """Receive incoming WhatsApp messages and respond via Claude."""
    body = await request.json()

    # Extract message data from webhook payload
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Ignore status updates (delivered, read, etc.)
        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        sender = message["from"]  # phone number
        msg_type = message["type"]
        contact_name = value.get("contacts", [{}])[0].get("profile", {}).get("name", "Paciente")

    except (KeyError, IndexError):
        logger.debug("Ignoring non-message webhook event")
        return {"status": "ok"}

    # Handle text messages only (for now)
    if msg_type == "text":
        user_text = message["text"]["body"]
    elif msg_type == "audio":
        # Placeholder for future audio transcription
        await send_whatsapp_message(
            sender,
            "Desculpe, ainda não consigo processar mensagens de áudio. "
            "Pode enviar a sua questão por texto? 🙏"
        )
        return {"status": "ok"}
    elif msg_type == "image":
        await send_whatsapp_message(
            sender,
            "Obrigada pela imagem! Para uma avaliação adequada, "
            "recomendamos agendar uma consulta presencial com tricoscopia digital. "
            "Deseja que eu ajude a marcar?"
        )
        return {"status": "ok"}
    else:
        await send_whatsapp_message(
            sender,
            "Desculpe, só consigo processar mensagens de texto neste momento. "
            "Como posso ajudá-lo(a)?"
        )
        return {"status": "ok"}

    logger.info(f"📩 Message from {contact_name} ({sender}): {user_text[:80]}")

    # Build conversation history
    history = get_conversation(sender)
    history.append({"role": "user", "content": user_text})

    # Call Claude
    assistant_reply = await call_claude(history, contact_name)

    # Store assistant reply in history
    history.append({"role": "assistant", "content": assistant_reply})
    save_conversation(sender, history)

    # Send response via WhatsApp
    await send_whatsapp_message(sender, assistant_reply)

    logger.info(f"📤 Reply to {contact_name}: {assistant_reply[:80]}")
    return {"status": "ok"}


# ─── Claude API ───────────────────────────────────────────────────────────────

async def call_claude(messages: list[dict], contact_name: str) -> str:
    """Send conversation to Claude and get a response."""
    # Inject patient name context
    system = SYSTEM_PROMPT + f"\n\nO paciente que está a falar chama-se: {contact_name}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
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
                    "messages": messages[-MAX_HISTORY:],  # trim to last N
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]

    except httpx.TimeoutException:
        logger.error("Claude API timeout")
        return (
            "Peço desculpa, estou com uma lentidão momentânea. "
            "Pode tentar novamente em alguns segundos? 🙏"
        )
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return (
            "Desculpe, ocorreu um erro no sistema. "
            "Por favor, tente novamente ou contacte-nos diretamente pelo telefone."
        )


# ─── WhatsApp API ─────────────────────────────────────────────────────────────

async def send_whatsapp_message(to: str, text: str):
    """Send a text message via WhatsApp Cloud API."""
    url = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            logger.debug(f"WhatsApp API response: {resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")


# ─── Conversation Memory ─────────────────────────────────────────────────────

def get_conversation(phone: str) -> list[dict]:
    """Retrieve conversation history for a phone number."""
    return conversations.get(phone, [])


def save_conversation(phone: str, history: list[dict]):
    """Save conversation history, trimming to MAX_HISTORY messages."""
    conversations[phone] = history[-MAX_HISTORY:]


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {
        "service": "APEX CAPILAR WhatsApp Agent",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }
