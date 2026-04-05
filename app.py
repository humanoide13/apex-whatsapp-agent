"""
APEX CAPILAR â WhatsApp AI Agent
Powered by Claude (Anthropic) + Meta WhatsApp Business Cloud API
"""

import os
import json
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from contextlib import asynccontextmanager

# âââ Config âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")           # Meta access token
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")     # Phone number ID
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "apex-capilar-2026")  # Webhook verify
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_HISTORY = 20  # messages to keep per conversation

# âââ Logging ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("apex-agent")

# âââ In-memory conversation store ââââââââââââââââââââââââââââââââââââââââââââ
# In production, swap this for Redis / a database
conversations: dict[str, list[dict]] = {}

# âââ System Prompt ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

SYSTEM_PROMPT = """Você é a Assistente Virtual da APEX CAPILAR, uma clínica especializada em restauração capilar localizada em São Félix da Marinha, Porto, Portugal.

## Identidade
Você é uma assistente profissional, acolhedora e elegante. Comunique com empatia, clareza e confiança. Trate cada paciente como único.

## Sobre a APEX CAPILAR
- Clínica de referência em tricologia clínica e restauração capilar cirúrgica
- Técnicas: FUE (Follicular Unit Extraction) e DHI (Direct Hair Implantation)
- Tratamentos complementares: mesoterapia capilar, PRP, protocolos tópicos, orais e injetáveis
- Consulta de avaliação tricológica completa com tricoscopia digital
- Responsável técnico: Dr. Khalil — Tricologista
- Website: apexcapilar.com

## Contactos e Agendamento
- Agendar online: https://apexcapilar.com/agendar.html
- Telefone: +351 932 348 037
- Website: https://apexcapilar.com

## Tom e Estilo de Comunicação
- Profissional mas acessível — nunca frio nem excessivamente informal
- Respostas concisas e bem estruturadas (é WhatsApp, não email)
- Use parágrafos curtos com quebras de linha para facilitar a leitura
- Máximo 1 emoji por mensagem, e apenas quando apropriado
- Responda no idioma do paciente (português por defeito)
- Nunca use markdown pesado — sem headers #, sem ** excessivo

## Suas Responsabilidades
1. Acolher o paciente com profissionalismo e empatia
2. Responder a dúvidas sobre serviços, técnicas e o processo de consulta
3. Quando o paciente quiser agendar, fornecer diretamente o link ou telefone
4. Fazer triagem inicial apenas quando o paciente demonstrar interesse em saber mais:
   - Há quanto tempo nota a queda/rarefação?
   - Histórico familiar de calvície?
   - Tratamentos anteriores?
   - Principal preocupação/expectativa?
5. Nunca insistir com perguntas se o paciente quer apenas agendar

## Regras Importantes
- Nunca faça diagnósticos — reforce que a avaliação presencial é essencial
- Nunca informe valores de procedimentos cirúrgicos — diga que dependem da avaliação individual
- Para consultas: informe que o valor pode ser confirmado ao agendar
- Se o paciente quer agendar, dê o link e telefone diretamente, sem fazer perguntas desnecessárias

## Informações Técnicas (para responder dúvidas)
- FUE vs DHI: ambas minimamente invasivas. FUE extrai folículos individualmente; DHI implanta com caneta Choi sem incisões prévias
- Recuperação: 7-10 dias para atividades normais; resultado final entre 9-12 meses
- Procedimento sob anestesia local, desconforto mínimo
- Resultados naturais e definitivos com cabelo do próprio paciente

## Exemplo de Resposta Ideal para Agendamento
"Com certeza! Pode agendar a sua consulta de avaliação tricológica de duas formas:

Pelo nosso site: apexcapilar.com/agendar.html
Ou por telefone: +351 932 348 037

Na consulta, o Dr. Khalil fará uma avaliação completa com tricoscopia digital para entender a sua situação e apresentar as melhores opções. Estamos à sua disposição!"
"""


# âââ FastAPI App ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ð APEX CAPILAR WhatsApp Agent started")
    yield
    logger.info("Agent shutting down")

app = FastAPI(title="APEX CAPILAR WhatsApp Agent", lifespan=lifespan)


# âââ Webhook Verification (GET) ââââââââââââââââââââââââââââââââââââââââââââââ

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta sends a GET request to verify the webhook URL."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("â Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("â Webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


# âââ Webhook Messages (POST) âââââââââââââââââââââââââââââââââââââââââââââââââ

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
            "Desculpe, ainda nÃ£o consigo processar mensagens de Ã¡udio. "
            "Pode enviar a sua questÃ£o por texto? ð"
        )
        return {"status": "ok"}
    elif msg_type == "image":
        await send_whatsapp_message(
            sender,
            "Obrigada pela imagem! Para uma avaliaÃ§Ã£o adequada, "
            "recomendamos agendar uma consulta presencial com tricoscopia digital. "
            "Deseja que eu ajude a marcar?"
        )
        return {"status": "ok"}
    else:
        await send_whatsapp_message(
            sender,
            "Desculpe, sÃ³ consigo processar mensagens de texto neste momento. "
            "Como posso ajudÃ¡-lo(a)?"
        )
        return {"status": "ok"}

    logger.info(f"ð© Message from {contact_name} ({sender}): {user_text[:80]}")

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

    logger.info(f"ð¤ Reply to {contact_name}: {assistant_reply[:80]}")
    return {"status": "ok"}


# âââ Claude API âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def call_claude(messages: list[dict], contact_name: str) -> str:
    """Send conversation to Claude and get a response."""
    # Inject patient name context
    system = SYSTEM_PROMPT + f"\n\nO paciente que estÃ¡ a falar chama-se: {contact_name}"

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
            "PeÃ§o desculpa, estou com uma lentidÃ£o momentÃ¢nea. "
            "Pode tentar novamente em alguns segundos? ð"
        )
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return (
            "Desculpe, ocorreu um erro no sistema. "
            "Por favor, tente novamente ou contacte-nos diretamente pelo telefone."
        )


# âââ WhatsApp API âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

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


# âââ Conversation Memory âââââââââââââââââââââââââââââââââââââââââââââââââââââ

def get_conversation(phone: str) -> list[dict]:
    """Retrieve conversation history for a phone number."""
    return conversations.get(phone, [])


def save_conversation(phone: str, history: list[dict]):
    """Save conversation history, trimming to MAX_HISTORY messages."""
    conversations[phone] = history[-MAX_HISTORY:]


# âââ Health Check âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.get("/")
async def health():
    return {
        "service": "APEX CAPILAR WhatsApp Agent",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }
