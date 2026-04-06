"""
APEX CAPILAR — WhatsApp AI Agent
Powered by Claude (Anthropic) + WhatsApp Business Cloud API
With conversation logging (SQLite) and admin dashboard.
"""

import os
import json
import logging
import httpx
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager

# ─── Config ───────────────────────────────────────────────────────────────────

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "apex-capilar-2026")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")  # set this on Railway!
PORT = int(os.getenv("PORT", "8000"))
MAX_HISTORY = 20
DB_PATH = os.getenv("DB_PATH", "/data/conversations.db")

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Voce e a assistente virtual da APEX CAPILAR, referencia em medicina capilar baseada em evidencia no Porto, Portugal.

A sua comunicacao deve refletir a excelencia e o prestigio da clinica em cada interacao. Voce e a primeira impressao que muitos pacientes terao da APEX CAPILAR — cada resposta deve transmitir confianca, competencia e cuidado genuino.

IDENTIDADE DA MARCA

A APEX CAPILAR representa uma abordagem diferenciada a saude capilar: rigor cientifico, tecnologia de ultima geracao e um acompanhamento clinico verdadeiramente personalizado. Cada plano de tratamento e construido com base na melhor evidencia disponivel e adaptado a realidade unica de cada paciente.

Na APEX CAPILAR, a tricologia e exercida como deve ser — com profundidade, atualizacao constante e compromisso com resultados reais.

SERVICOS

Consulta de Avaliacao Tricologica
Analise completa com tricoscopia digital de alta resolucao, diagnostico diferencial e elaboracao de um plano de tratamento integrado e personalizado.

Transplante Capilar FUE (Follicular Unit Extraction)
Tecnica minimamente invasiva de extracao folicular individual. Sem cicatriz linear, com recuperacao rapida e resultados naturais.

Transplante Capilar DHI (Direct Hair Implantation)
Implantacao direta com caneta Choi, permitindo maxima precisao no angulo, direcao e densidade. Ideal para zonas que exigem naturalidade absoluta.

Protocolos Clinicos Personalizados
Tratamentos topicos, orais e injetaveis, desenhados a medida de cada paciente e ajustados ao longo do acompanhamento clinico.

CONTACTOS

Website: apexcapilar.com
Agendamento online: apexcapilar.com/agendar.html
Telefone (apenas chamadas): +351 932 348 037
WhatsApp: +351 936 892 039
E-mail: contacto@apexcapilar.com

LOCALIZACAO E HORARIO

As consultas realizam-se no Centro de Medicina Integrativa Dra. Ana Moreira.
Av. da Boavista 1681, 1o andar, 4100-132 Porto, Portugal.
Localizacao no Google Maps: https://share.google/AUS6FGq85bN2HESLY

Horario de consultas:
  Segundas-feiras, das 9h00 as 13h00
  Sabados, das 9h00 as 13h00

DIRECTRIZES DE AGENDAMENTO

Quando o paciente manifestar interesse em agendar, apresente as opcoes de forma clara e acessivel:

  Agendamento online: apexcapilar.com/agendar.html
  Por telefone: +351 932 348 037

Nao faca triagem clinica nem coloque multiplas perguntas antes de disponibilizar os meios de agendamento. O objetivo e facilitar o acesso do paciente a consulta.

PACIENTES COM DUVIDAS POS-CONSULTA

Quando o paciente indicar que ja realizou uma consulta e apresentar duvidas sobre o seu caso, NAO tente responder a questoes clinicas especificas. Voce nao tem acesso ao historial clinico nem ao que foi discutido em consulta.

Responda com empatia genuina e encaminhe para contacto direto, sugerindo:

  Telefone: +351 932 348 037
  E-mail: contacto@apexcapilar.com
  Consulta de seguimento: apexcapilar.com/agendar.html

QUANDO INCLUIR O E-MAIL

Inclua contacto@apexcapilar.com apenas nestas situacoes:
  Duvidas pos-consulta ou questoes clinicas especificas
  Envio de documentos, exames ou fotografias
  Mensagem de erro do sistema
  Quando o paciente solicita explicitamente um e-mail

Nas demais situacoes, evite sobrecarregar a resposta com informacao desnecessaria.

VOZ E TOM DA MARCA

Personalidade: Profissional, calorosa, sofisticada. Como uma concierge de saude num ambiente clinico de excelencia — acolhedora sem ser informal, competente sem ser distante.

Estrutura das respostas:
  Escreva em paragrafos bem construidos, com frases completas e elegantes.
  Separe ideias distintas com quebras de linha para facilitar a leitura.
  Use uma estrutura clara e respirada — sem paredes de texto, mas tambem sem listas mecanicas.
  Cada resposta deve fluir naturalmente, como uma conversa presencial de qualidade.

Regras absolutas:
  Portugues europeu (PT-PT), sempre.
  Trate o paciente por "voce", com respeito e proximidade.
  Nunca utilize emojis, asteriscos, markdown, bold, italico ou qualquer formatacao especial. Apenas texto limpo, elegante e bem pontuado.
  Nunca faca diagnosticos medicos — encaminhe para consulta presencial.
  Nunca revele valores de cirurgias ou procedimentos. Os valores sao personalizados e definidos apos avaliacao presencial.
  Nunca faca mais do que uma pergunta por mensagem.
  Se nao souber a resposta, encaminhe para contacto direto com transparencia e cortesia.

Gestao da conversa:
  Cumprimente o paciente APENAS na primeira mensagem. Nas seguintes, responda diretamente ao que foi perguntado.
  Mantenha as respostas concisas mas substantivas — cada palavra deve acrescentar valor.
  Responda com foco e precisao. Nao repita informacao ja fornecida.
  Encerre cada resposta com uma abertura natural para o paciente continuar a conversa ou com uma indicacao clara de como dar o proximo passo.

PRIMEIRA MENSAGEM (apenas na primeira interacao)

"Bem-vindo a APEX CAPILAR.

Somos uma clinica dedicada a medicina capilar baseada em evidencia, com foco em diagnostico preciso, tratamentos atualizados e acompanhamento personalizado.

Estou ao seu dispor para esclarecer qualquer questao sobre os nossos servicos ou para facilitar o agendamento da sua consulta.

Em que posso ajuda-lo?"

MENSAGENS SEGUINTES

Responda diretamente ao que o paciente perguntou, sem repetir saudacoes ou apresentacoes. Mantenha o tom premium e acolhedor em cada interacao."""

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("apex-agent")

# ─── Database ─────────────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT 'Cliente',
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            msg_type TEXT NOT NULL DEFAULT 'text',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON messages(phone)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON messages(created_at)")
    conn.commit()
    conn.close()
    log.info(f"Database ready at {DB_PATH}")

def db_save_message(phone: str, name: str, role: str, content: str, msg_type: str = "text"):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO messages (phone, name, role, content, msg_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (phone, name, role, content, msg_type, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

def db_get_conversations_list():
    """Return summary of all conversations."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT phone, name,
               COUNT(*) as total_messages,
               MIN(created_at) as first_message,
               MAX(created_at) as last_message
        FROM messages
        GROUP BY phone
        ORDER BY MAX(created_at) DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_conversation(phone: str):
    """Return all messages for a phone number."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM messages WHERE phone = ? ORDER BY created_at ASC",
        (phone,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_history_for_claude(phone: str) -> list[dict]:
    """Return last MAX_HISTORY messages as Claude-format dicts."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE phone = ? AND role IN ('user','assistant') ORDER BY created_at ASC",
        (phone,),
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def db_is_first_message(phone: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM messages WHERE phone = ?", (phone,)).fetchone()[0]
    conn.close()
    return count == 0

# ─── In-memory fallback (keeps working if DB fails) ──────────────────────────

conversations: dict[str, list[dict]] = {}

# ─── Auth helper ──────────────────────────────────────────────────────────────

def verify_dashboard_token(request: Request):
    """Check token via query param or Authorization header."""
    token = request.query_params.get("token", "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not DASHBOARD_TOKEN:
        raise HTTPException(503, "DASHBOARD_TOKEN not configured on server")
    if not secrets.compare_digest(token, DASHBOARD_TOKEN):
        raise HTTPException(403, "Invalid token")
    return True

# ─── App ──────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("APEX CAPILAR WhatsApp Agent started")
    yield
    log.info("Agent shutting down")

app = FastAPI(title="APEX CAPILAR WhatsApp Agent", lifespan=lifespan)

@app.get("/")
async def health():
    return {
        "status": "online",
        "service": "APEX CAPILAR WhatsApp Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ─── Webhook ──────────────────────────────────────────────────────────────────

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
            # Save inbound message
            db_save_message(sender, sender_name, "user", text, "text")
            reply = await call_claude(sender, sender_name)
            # Save outbound reply
            db_save_message(sender, sender_name, "assistant", reply, "text")
            await send_whatsapp_message(sender, reply)
            log.info(f"Reply to {sender_name}: {reply[:80]}...")
        else:
            log.info(f"Non-text message ({msg_type}) from {sender_name}")
            fallback = "De momento apenas processamos mensagens de texto.\n\nPara falar connosco diretamente, ligue para +351 932 348 037."
            db_save_message(sender, sender_name, "user", f"[{msg_type}]", msg_type)
            db_save_message(sender, sender_name, "assistant", fallback, "text")
            await send_whatsapp_message(sender, fallback)
    except Exception as e:
        log.error(f"Webhook processing error: {e}")
    return {"status": "ok"}

# ─── Claude ───────────────────────────────────────────────────────────────────

async def call_claude(sender: str, sender_name: str) -> str:
    is_first = db_is_first_message(sender)
    # After saving the user message, this will be False for subsequent,
    # but we already saved, so check count == 1
    history = db_get_history_for_claude(sender)
    is_first = len(history) <= 1
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
                    "messages": history[-MAX_HISTORY:],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return (
            "Pedimos desculpa, mas de momento nao foi possivel processar o seu pedido.\n\n"
            "Por favor, contacte-nos diretamente:\n"
            "Telefone: +351 932 348 037\n"
            "E-mail: contacto@apexcapilar.com\n"
            "Website: apexcapilar.com"
        )

# ─── WhatsApp send ────────────────────────────────────────────────────────────

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

# ─── API: Conversations (JSON) ───────────────────────────────────────────────

@app.get("/api/conversations")
async def api_conversations(auth: bool = Depends(verify_dashboard_token)):
    return db_get_conversations_list()

@app.get("/api/conversations/{phone}")
async def api_conversation_detail(phone: str, auth: bool = Depends(verify_dashboard_token)):
    msgs = db_get_conversation(phone)
    if not msgs:
        raise HTTPException(404, "No conversation found")
    return msgs

# ─── Dashboard (HTML) ────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>APEX CAPILAR — Conversas</title>
<style>
  :root { --gold: #c9a84c; --bg: #0a0a0a; --surface: #111; --surface2: #161616; --border: #1e1e1e; --text: #e8e8e8; --muted: #777; --patient-bg: #1b2b1b; --patient-text: #c8e6c8; --bot-bg: #1a1a28; --bot-text: #c8c8e6; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); }
  .header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .header h1 { font-size: 17px; font-weight: 700; color: var(--gold); letter-spacing: 0.5px; }
  .header .subtitle { font-size: 12px; color: var(--muted); }
  .header .status { font-size: 11px; color: #4a9; background: rgba(68,170,153,0.1); padding: 3px 10px; border-radius: 10px; }
  .container { display: flex; height: calc(100vh - 56px); }

  .sidebar { width: 340px; border-right: 1px solid var(--border); overflow-y: auto; background: var(--bg); }
  .sidebar-title { padding: 14px 18px 10px; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); }
  .conv-item { padding: 14px 18px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background .15s; }
  .conv-item:hover, .conv-item.active { background: var(--surface2); }
  .conv-top { display: flex; justify-content: space-between; align-items: baseline; }
  .conv-name { font-weight: 600; font-size: 14px; color: var(--text); }
  .conv-date { font-size: 11px; color: var(--muted); }
  .conv-phone { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .conv-preview { font-size: 12px; color: #555; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .conv-count { font-size: 10px; color: var(--gold); background: rgba(201,168,76,0.12); padding: 2px 7px; border-radius: 8px; margin-top: 4px; display: inline-block; }

  .chat-area { flex: 1; display: flex; flex-direction: column; background: var(--bg); }
  .chat-header { padding: 14px 24px; border-bottom: 1px solid var(--border); background: var(--surface); display: flex; align-items: center; justify-content: space-between; }
  .chat-header-info h2 { font-size: 15px; font-weight: 600; color: var(--text); }
  .chat-header-info .phone { font-size: 12px; color: var(--muted); margin-top: 1px; }
  .chat-back { display: none; background: none; border: none; color: var(--gold); font-size: 14px; cursor: pointer; padding: 6px 10px; }

  .chat-messages { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 6px; }
  .date-sep { text-align: center; margin: 16px 0 10px; }
  .date-sep span { font-size: 11px; color: var(--muted); background: var(--surface); padding: 4px 14px; border-radius: 10px; }

  .msg-row { display: flex; flex-direction: column; max-width: 75%; gap: 2px; }
  .msg-row.patient { align-self: flex-end; align-items: flex-end; }
  .msg-row.bot { align-self: flex-start; align-items: flex-start; }
  .msg-sender { font-size: 11px; font-weight: 600; margin-bottom: 1px; padding: 0 4px; }
  .msg-row.patient .msg-sender { color: #6b9; }
  .msg-row.bot .msg-sender { color: var(--gold); }

  .msg-bubble { padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.55; white-space: pre-wrap; word-wrap: break-word; }
  .msg-row.patient .msg-bubble { background: var(--patient-bg); color: var(--patient-text); border-bottom-right-radius: 4px; }
  .msg-row.bot .msg-bubble { background: var(--bot-bg); color: var(--bot-text); border-bottom-left-radius: 4px; }

  .msg-time { font-size: 10px; color: #555; padding: 0 4px; }

  .empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: #333; gap: 8px; }
  .empty-icon { font-size: 40px; opacity: 0.3; }
  .empty-text { font-size: 14px; }

  @media (max-width: 700px) {
    .sidebar { width: 100%; }
    .chat-area { display: none; }
    .container.chat-open .sidebar { display: none; }
    .container.chat-open .chat-area { display: flex; }
    .container.chat-open .chat-back { display: block; }
    .msg-row { max-width: 88%; }
  }
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>APEX CAPILAR</h1>
    <span class="subtitle">Painel de Conversas</span>
  </div>
  <span class="status">Bot activo</span>
</div>
<div class="container" id="container">
  <div class="sidebar">
    <div class="sidebar-title">Conversas recentes</div>
    <div id="sidebar"></div>
  </div>
  <div class="chat-area" id="chatArea">
    <div class="empty">
      <div class="empty-icon">&#9993;</div>
      <div class="empty-text">Selecione uma conversa para visualizar</div>
    </div>
  </div>
</div>
<script>
const TOKEN = new URLSearchParams(location.search).get('token') || '';
const API = (path) => path + '?token=' + encodeURIComponent(TOKEN);

function formatDate(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diff = (now - d) / 86400000;
  if (diff < 1 && d.getDate() === now.getDate()) return 'Hoje';
  if (diff < 2) return 'Ontem';
  return d.toLocaleDateString('pt-PT', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatTime(iso) {
  return new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatHour(iso) {
  return new Date(iso).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' });
}

async function load() {
  const res = await fetch(API('/api/conversations'));
  if (!res.ok) { document.getElementById('sidebar').innerHTML = '<div class="empty"><div class="empty-text">Acesso negado</div></div>'; return; }
  const convs = await res.json();
  const sb = document.getElementById('sidebar');
  sb.innerHTML = convs.map(c => `
    <div class="conv-item" onclick="openChat('${c.phone}', '${(c.name||'').replace(/'/g,"\\\\'")}')">
      <div class="conv-top">
        <span class="conv-name">${c.name || 'Sem nome'}</span>
        <span class="conv-date">${formatDate(c.last_message)}</span>
      </div>
      <div class="conv-phone">+${c.phone}</div>
      <span class="conv-count">${c.total_messages} mensagens</span>
    </div>
  `).join('');
}

async function openChat(phone, name) {
  document.getElementById('container').classList.add('chat-open');
  const res = await fetch(API('/api/conversations/' + phone));
  const msgs = await res.json();

  let lastDate = '';
  let html = '';
  msgs.forEach(m => {
    const msgDate = formatDate(m.created_at);
    if (msgDate !== lastDate) {
      html += '<div class="date-sep"><span>' + msgDate + '</span></div>';
      lastDate = msgDate;
    }
    const isPatient = m.role === 'user';
    const cls = isPatient ? 'patient' : 'bot';
    const sender = isPatient ? (name || 'Paciente') : 'APEX CAPILAR';
    html += '<div class="msg-row ' + cls + '">';
    html += '<div class="msg-sender">' + sender + '</div>';
    html += '<div class="msg-bubble">' + m.content.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>';
    html += '<div class="msg-time">' + formatTime(m.created_at) + '</div>';
    html += '</div>';
  });

  const ca = document.getElementById('chatArea');
  ca.innerHTML =
    '<div class="chat-header">' +
      '<button class="chat-back" onclick="document.getElementById(\\'container\\').classList.remove(\\'chat-open\\')">&#8592; Voltar</button>' +
      '<div class="chat-header-info"><h2>' + (name||'Paciente') + '</h2><div class="phone">+' + phone + '</div></div>' +
    '</div>' +
    '<div class="chat-messages">' + html + '</div>';
  ca.querySelector('.chat-messages').scrollTop = 999999;
}

load();
setInterval(load, 30000);
</script>
</body>
</html>"""

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
