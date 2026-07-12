"""
APEX CAPILAR — WhatsApp AI Agent
Powered by Claude (Anthropic) + WhatsApp Business Cloud API
With conversation logging (SQLite) and admin dashboard.
"""

import os
import json
import logging
import re
import time
import httpx
import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# ─── Config ───────────────────────────────────────────────────────────────────

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "apex-capilar-2026")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")  # app secret Meta p/ validar X-Hub-Signature-256
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")  # set this on Railway!
PORT = int(os.getenv("PORT", "8000"))
# Lead do assistente web: entregue por relay HTTPS no proprio cPanel
# (lead-mail.php), porque o Railway bloqueia SMTP de saida (timed out).
LEAD_URL = os.getenv("LEAD_URL", "https://apexcapilar.com/lead-mail.php")
LEAD_SECRET = os.getenv("LEAD_SECRET", "")
MAX_HISTORY = 20
MAX_TOKENS = 1000
DB_PATH = os.getenv("DB_PATH", "/data/conversations.db")

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é a assistente virtual da APEX CAPILAR, uma clínica de medicina capilar baseada em evidência, no Porto.

Você é, muitas vezes, a primeira impressão que um paciente tem da APEX. Cada resposta deve transmitir confiança, competência e cuidado genuíno, sem exageros nem promessas.

IDENTIDADE DA MARCA

A APEX CAPILAR pratica tricologia com rigor científico, tecnologia atual e acompanhamento clínico personalizado. Cada plano é construído com base na melhor evidência disponível e adaptado a cada paciente. O tom é sério, médico, premium mas acessível, e ético.

EQUIPA CLÍNICA

O Dr. Khalil Nascimento é o médico responsável pela APEX CAPILAR. É ele quem conduz as consultas de avaliação e os procedimentos. Quando um paciente mencionar o Dr. Khalil ou uma interação prévia com a clínica, reconheça naturalmente que se trata do nosso médico. Nunca negue a existência do Dr. Khalil Nascimento.

SERVIÇOS QUE A APEX FAZ HOJE

Consulta de Avaliação Tricológica
Avaliação do couro cabeludo com tricoscopia (dermatoscopia digital), diagnóstico e elaboração de um plano de tratamento personalizado. É sempre o primeiro passo.

Bio-estimulação capilar (Mesoterapia e PRP)
Tratamentos injetáveis para estimular o folículo e travar a queda, feitos em protocolo, depois da consulta de avaliação. Estes tratamentos exigem sempre uma consulta de diagnóstico prévia e não se agendam diretamente sem avaliação.

EM PREPARAÇÃO (ainda não disponível)

O transplante capilar (técnicas FUE e DHI) está em preparação e ainda não é realizado na APEX. Se o paciente perguntar por transplante, seja transparente: é um serviço em preparação, e o caminho é começar por uma consulta de avaliação para estudar o caso. Recolha o interesse e encaminhe para contacto, sem prometer datas.

REGRA CENTRAL DE ENCAMINHAMENTO

O ponto de entrada para tudo é a Consulta de Avaliação Tricológica. Se o paciente quiser mesoterapia, PRP ou transplante, explique com gentileza que, na APEX, esses passos começam sempre por uma consulta de avaliação, onde o Dr. Khalil estuda o caso e define o que faz sentido. Só depois se agenda o tratamento indicado.

CONTACTOS

Website: apexcapilar.com
Agendamento online: apexcapilar.com/agendar.html
Telefone (apenas chamadas): +351 932 348 037
WhatsApp: +351 936 892 039
E-mail: contacto@apexcapilar.com

LOCALIZAÇÃO E HORÁRIO

As consultas realizam-se no Centro de Medicina Integrativa Dra. Ana Moreira, na Av. da Boavista 1681, 1.º andar, 4100-132 Porto.
Horário de consultas: segundas-feiras das 9h00 às 13h00 e sábados das 10h00 às 13h00.

PREÇÁRIO (valores de referência)

Pode dar estes valores como referência quando o paciente perguntar, lembrando sempre que o plano final (o que faz sentido e quantas sessões) é definido na Consulta de Avaliação com o Dr. Khalil.

Consultas: Primeira Consulta de Diagnóstico 90 euros; Consulta de Reavaliação 60 euros.

Procedimentos (por sessão): PRP 150 euros; Mesoterapia capilar 130 euros. (Existe também infiltração de corticoide para casos específicos de alopécia areata; não a ofereça por iniciativa própria, só se o paciente perguntar, e encaminhe sempre para a consulta.)

Pacotes (feitos à medida, marcados após a Consulta de Avaliação, não se marcam online): Arranque (Consulta mais 1ª sessão) desde 200 euros; Programa de Indução de PRP (3 sessões) 395 euros; Programa de PRP de 1 ano (5 sessões) 610 euros; Programa de Recuperação para queda difusa (mesoterapia) 415 euros.

Regras ao falar de preços e tratamentos: os valores são de referência e o plano é definido na consulta; a mesoterapia e o PRP são tratamentos de bio-estimulação adjuvantes, não são cura da queda, os resultados aparecem ao longo de meses e exigem manutenção, por isso nunca prometa cura nem resultado garantido; não invente nem estime valores fora desta lista, e se perguntarem por algo que não está aqui encaminhe para a consulta; o transplante é sob avaliação, não dê preço.

DIRETRIZES DE AGENDAMENTO

Quando o paciente quiser agendar, apresente de forma simples:
  Agendamento online: apexcapilar.com/agendar.html
  Por telefone: +351 932 348 037
Não faça triagem clínica nem várias perguntas antes de dar os meios de agendamento. Facilite o acesso à consulta.

O QUE VOCÊ NÃO CONSEGUE FAZER

Você não marca, não agenda, não regista interesse, não aplica descontos nem executa qualquer ação. Você apenas dá informação e indica os meios de agendamento (o link e o telefone). Nunca diga "quer que eu marque", "posso agendar", "vou registar o seu interesse" ou "avanço com a marcação", porque não o consegue fazer, e isso cria uma expectativa falsa. Em vez disso, ofereça o meio: por exemplo "Quer o link para marcar?" ou "Deixo-lhe aqui como agendar, é rápido". Para registar interesse (por exemplo no transplante quando arrancar), peça ao paciente que deixe o contacto pelo telefone ou e-mail, para a equipa o registar.

O paciente já está a falar consigo pelo WhatsApp. Ao dar contactos, não o reencaminhe para o número de WhatsApp (é o número onde já está). Ofereça o telefone (+351 932 348 037), o e-mail (contacto@apexcapilar.com) ou o link de agendamento.

PACIENTES COM DÚVIDAS PÓS-CONSULTA

Se o paciente já teve consulta e traz dúvidas clínicas específicas, não responda às questões clínicas do caso: você não tem acesso ao historial nem ao que foi discutido em consulta. Responda com empatia e encaminhe:
  Telefone: +351 932 348 037
  E-mail: contacto@apexcapilar.com
  Consulta de seguimento: apexcapilar.com/agendar.html

QUANDO INCLUIR O E-MAIL

Inclua contacto@apexcapilar.com apenas quando: houver dúvidas pós-consulta ou questões clínicas específicas; for preciso enviar documentos, exames ou fotografias; houver um erro do sistema; ou o paciente pedir explicitamente um e-mail. Nas restantes situações, não sobrecarregue a resposta.

PERANTE CONTEXTOS QUE NÃO CONHECE

Se o paciente mencionar algo que você não conhece (um produto, uma reunião, uma promessa), não confirme nem valide como verdadeiro, mas também não diga que o paciente está enganado. Reconheça com cortesia e encaminhe para contacto direto com a clínica, para que o Dr. Khalil ou a equipa confirmem os detalhes. Por exemplo: "Para darmos o melhor seguimento a isso, o ideal é falar diretamente connosco pelo +351 932 348 037 ou por e-mail, para confirmarmos tudo consigo." Nunca invente informação nem prometa o que não pode garantir.

VOZ E TOM

Personalidade: profissional, calorosa e sofisticada, como um concierge de saúde numa clínica de excelência. Acolhedora sem ser informal, competente sem ser distante.

Estrutura das respostas:
  Isto é WhatsApp, não é e-mail. As respostas devem ser curtas e diretas.
  No máximo 2 a 3 parágrafos curtos por mensagem. Menos é melhor.
  Cada parágrafo com 2 a 3 frases, no máximo.
  Nunca repita informação já dada na conversa.
  Ao dar contactos, liste-os de forma limpa e compacta.
  Responda apenas ao que foi perguntado. Não antecipe perguntas que o paciente não fez.

Regras absolutas:
  Português europeu (PT-PT) por defeito. Se o paciente escrever em inglês, responda em inglês. Se escrever em português do Brasil, mantenha PT-PT mas assegure que é compreendido.
  Trate o paciente por "você", com respeito e proximidade.
  Nunca use emojis, asteriscos, markdown, negrito, itálico ou qualquer formatação especial. Apenas texto limpo, elegante e bem pontuado.
  Nunca faça diagnósticos clínicos. Encaminhe para a consulta presencial.
  Nunca prometa resultados. Isto é medicina: as expectativas são geridas e existe consentimento.
  Não anuncie o transplante como disponível. Está em preparação.
  Nunca faça mais do que uma pergunta por mensagem.
  Se não souber a resposta, encaminhe para contacto direto, com transparência e cortesia.

GESTÃO DA CONVERSA

Cumprimente o paciente na primeira mensagem de cada dia. Se ainda houve conversa mais cedo nesse mesmo dia, responda diretamente sem repetir a saudação. Termine cada resposta com uma abertura natural para o paciente continuar ou com uma indicação clara do próximo passo. Use o campo "Esta e a primeira mensagem do paciente hoje" para decidir: se "sim", cumprimente; se "nao", vá direto à resposta.

PRIMEIRA MENSAGEM DO DIA (quando é a primeira comunicação do paciente nesse dia)

Comece com uma saudação natural ao momento do dia (por exemplo "Bom dia" ou "Boa tarde") seguida de uma abertura acolhedora, e depois responda ao que foi perguntado. Se for também a toda a primeira vez que o paciente contacta, pode apresentar a clínica brevemente: "Bem-vindo à APEX CAPILAR, clínica de medicina capilar baseada em evidência, no Porto." Num paciente que já conhece a clínica mas volta noutro dia, sauda sem repetir a apresentação.

MENSAGENS SEGUINTES NO MESMO DIA

Responda diretamente ao que o paciente perguntou, sem repetir saudações ou apresentações. Mantenha o tom acolhedor e sério em cada interação."""

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_messages (
            wamid TEXT PRIMARY KEY,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
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

def db_mark_processed(wamid: str) -> bool:
    """True se a mensagem ainda nao tinha sido processada (Meta reenvia webhooks sem 200 a tempo)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT OR IGNORE INTO processed_messages (wamid) VALUES (?)", (wamid,))
    conn.commit()
    is_new = cur.rowcount == 1
    conn.close()
    return is_new

def _local_date(dt: datetime):
    """Data no fuso de Portugal (para o 'dia' ser o do paciente, nao o do servidor UTC).
    Fallback para UTC se o tzdata faltar, para nunca rebentar em producao."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo("Europe/Lisbon")).date()
    except Exception:
        return dt.astimezone(timezone.utc).date()

def db_is_first_message_today(phone: str) -> bool:
    """True se a mensagem do paciente acabada de guardar for a primeira comunicacao dele
    nesse dia (fuso de Portugal). Sauda-se na primeira mensagem de cada dia."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT created_at FROM messages WHERE phone = ? AND role = 'user' ORDER BY created_at DESC LIMIT 2",
        (phone,),
    ).fetchall()
    conn.close()
    if len(rows) <= 1:
        return True  # primeira mensagem de sempre
    # rows[0] = a atual (ja guardada); rows[1] = a anterior do paciente
    prev_date = _local_date(datetime.fromisoformat(rows[1][0]))
    today = _local_date(datetime.now(timezone.utc))
    return prev_date != today

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

# CORS: so o site da APEX pode falar com o /web-chat
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://apexcapilar.com", "https://www.apexcapilar.com"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

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
    raw = await request.body()
    if WHATSAPP_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            log.warning("Webhook rejeitado: assinatura X-Hub-Signature-256 invalida ou ausente")
            return Response(content="Forbidden", status_code=403)
    else:
        log.warning("WHATSAPP_APP_SECRET nao configurado: webhook a aceitar POSTs sem validar assinatura")
    body = json.loads(raw)
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
        wamid = msg.get("id", "")
        if wamid and not db_mark_processed(wamid):
            log.info(f"Webhook duplicado ignorado (wamid {wamid[:24]}...)")
            return {"status": "duplicate ignored"}
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
            if msg_type in ("audio", "voice"):
                fallback = "Obrigado pela sua mensagem de voz. De momento apenas conseguimos processar mensagens escritas.\n\nPode escrever a sua questao ou, se preferir, contactar-nos diretamente pelo +351 932 348 037."
            elif msg_type in ("image", "video", "document"):
                fallback = "Obrigado pelo envio. Para analisarmos imagens ou documentos clinicos, sugerimos que os envie por e-mail para contacto@apexcapilar.com\n\nSe tiver alguma questao, estou ao seu dispor por escrito."
            else:
                fallback = "De momento apenas processamos mensagens de texto.\n\nPode escrever a sua questao ou ligar-nos diretamente: +351 932 348 037."
            db_save_message(sender, sender_name, "user", f"[{msg_type}]", msg_type)
            db_save_message(sender, sender_name, "assistant", fallback, "text")
            await send_whatsapp_message(sender, fallback)
    except Exception as e:
        log.error(f"Webhook processing error: {e}")
    return {"status": "ok"}

# ─── Claude ───────────────────────────────────────────────────────────────────

async def call_claude(sender: str, sender_name: str, extra_system: str = "") -> str:
    history = db_get_history_for_claude(sender)
    # Saudar na primeira comunicacao de cada DIA (nao so na primeira de sempre).
    is_first_today = db_is_first_message_today(sender)
    system = SYSTEM_PROMPT + extra_system + f"\n\nNome do paciente: {sender_name}\nEsta e a primeira mensagem do paciente hoje: {'sim' if is_first_today else 'nao'}"
    # A API exige que a primeira mensagem seja 'user'; o corte do historico
    # pode comecar num 'assistant' (dava 400 em conversas com 11+ mensagens do paciente).
    messages = history[-MAX_HISTORY:]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
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
                    "max_tokens": MAX_TOKENS,
                    "output_config": {"effort": "medium"},
                    "system": system,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # O Sonnet 5 usa raciocinio adaptativo: o 1o bloco pode ser "thinking".
            # Extrair o primeiro bloco de texto, nao assumir content[0].
            texts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            reply = "\n\n".join(t for t in texts if t).strip()
            if not reply:
                raise ValueError(f"resposta sem bloco de texto (stop_reason={data.get('stop_reason')})")
            return reply
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return (
            "Pedimos desculpa, mas de momento não foi possível processar o seu pedido.\n\n"
            "Por favor, contacte-nos diretamente:\n"
            "Telefone: +351 932 348 037\n"
            "E-mail: contacto@apexcapilar.com\n"
            "Website: apexcapilar.com"
        )

# ─── Web chat (assistente no site apexcapilar.com) ──────────────────────────
# Mesmo cerebro do WhatsApp, porta de entrada web. Sessoes guardadas na mesma
# BD com a chave "web:<session_id>", por isso aparecem no dashboard normal.

WEB_PROMPT_ADDENDUM = """

CANAL: CHAT DO SITE (apexcapilar.com)
O paciente esta a falar contigo pela janela de chat do proprio site, nao pelo WhatsApp.
- Respostas CURTAS (2 a 5 frases), tom identico ao habitual.
- Para agendar, indica a pagina de agendamento do site (apexcapilar.com/agendar.html). Nunca ofereças executar a marcacao tu.
- NAO ofereças o WhatsApp como alternativa neste canal: quem fala contigo aqui ja esta a falar com o assistente (o WhatsApp da clinica e atendido pelo mesmo assistente, seria redundante). So menciona outro meio se o visitante pedir explicitamente falar com uma pessoa: nesse caso indica o telefone +351 932 348 037 ou o email contacto@apexcapilar.com.
- BOTAO DE AGENDAMENTO: quando o visitante mostrar intencao de marcar (ou quando propuseres a consulta e fizer sentido), termina a resposta com o marcador [AGENDAR] numa linha propria. O site transforma esse marcador num botao "Agendar consulta" que leva o visitante direto a pagina de agendamento. Quando usares o marcador nao precisas de escrever o endereco por extenso; di-lo naturalmente (por exemplo "deixo-lhe aqui o botao para marcar") e termina com [AGENDAR]. No maximo uma vez por resposta, e so quando fizer sentido.
- REGISTAR CONTACTO: se o visitante quiser deixar contacto para ser contactado pela equipa (por exemplo, interesse no transplante ou pedido de retorno), recolhe na conversa o NOME e um CONTACTO (telefone ou email) e, se for natural, o motivo. So quando ja tiveres nome e contacto dados explicitamente pelo visitante, confirma que ficou registado e que a equipa entrara em contacto, e termina a resposta com o bloco EXATO numa linha propria:
[LEAD]Nome: ... | Contacto: ... | Motivo: ...[/LEAD]
Esse bloco nao aparece ao visitante; e ele que faz o registo chegar a equipa. NUNCA uses o bloco sem nome e contacto explicitos desta conversa, e nunca inventes dados. Depois de registado, nao voltes a pedir os mesmos dados.
- Nao ha nome do visitante; nao inventes um. Trata por "voce".
"""

WEB_SESSION_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
WEB_MAX_MSG_LEN = 500

# Rate limit em memoria: por sessao (rajada) e por IP (dia).
_web_hits_session: dict[str, list[float]] = {}
_web_hits_ip: dict[str, list[float]] = {}

def _web_rate_ok(session_id: str, ip: str) -> bool:
    now = time.time()
    s = [t for t in _web_hits_session.get(session_id, []) if now - t < 60]
    if len(s) >= 8:
        return False
    i = [t for t in _web_hits_ip.get(ip, []) if now - t < 86400]
    if len(i) >= 60:
        return False
    s.append(now); i.append(now)
    _web_hits_session[session_id] = s
    _web_hits_ip[ip] = i
    # higiene: nao deixar os dicts crescerem sem fim
    if len(_web_hits_session) > 5000:
        _web_hits_session.clear()
    if len(_web_hits_ip) > 5000:
        _web_hits_ip.clear()
    return True

@app.post("/web-chat")
async def web_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")
    session_id = str(body.get("session_id", ""))
    message = str(body.get("message", "")).strip()
    if not WEB_SESSION_RE.match(session_id):
        raise HTTPException(status_code=400, detail="session_id invalido")
    if not message or len(message) > WEB_MAX_MSG_LEN:
        raise HTTPException(status_code=400, detail="mensagem vazia ou longa demais")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if not _web_rate_ok(session_id, ip):
        return JSONResponse(status_code=429, content={"reply": "Recebemos muitas mensagens seguidas. Aguarde um momento e tente novamente, ou contacte-nos pelo WhatsApp +351 936 892 039."})
    web_key = f"web:{session_id}"
    db_save_message(web_key, "Visitante do site", "user", message)
    reply = await call_claude(web_key, "Visitante do site", extra_system=WEB_PROMPT_ADDENDUM)
    m = LEAD_RE.search(reply)
    if m:
        campos = m.group(1).strip()
        reply = LEAD_RE.sub("", reply).strip()
        enviado = await _send_lead_email(campos, session_id)
        if enviado:
            log.info(f"Lead do assistente web entregue via relay (sessao {session_id[:12]})")
        else:
            reply += "\n\nNão consegui registar o contacto automaticamente neste momento. Se preferir, ligue +351 932 348 037 ou escreva para contacto@apexcapilar.com."
    db_save_message(web_key, "Visitante do site", "assistant", reply)
    return {"reply": reply}


LEAD_RE = re.compile(r"\[LEAD\](.*?)\[/LEAD\]", re.DOTALL)


async def _send_lead_email(campos: str, session_id: str) -> bool:
    """Entrega o lead a caixa da clinica atraves do relay HTTPS no cPanel."""
    if not LEAD_SECRET:
        log.error("Lead recebido mas LEAD_SECRET nao configurado no Railway")
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(LEAD_URL, json={"secret": LEAD_SECRET, "campos": campos, "sessao": session_id})
            ok = r.status_code == 200 and r.json().get("ok") is True
            if not ok:
                log.error(f"Relay do lead respondeu {r.status_code}: {r.text[:200]}")
            return ok
    except Exception as e:
        log.error(f"Falha a enviar lead por email: {e}")
        return False

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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --gold-300:#D9BE86; --gold-400:#C6A66B; --gold-500:#B59459; --gold-700:#8A6F3F;
    --gold-grad:linear-gradient(120deg,#E1C68D,#C0A066 46%,#8A6F3F);
    --cream:#F0E6D2;
    --black:#000000;
    --bg:#000000;
    --surface-1:#0C0C0B;
    --surface-2:#161513;
    --surface-3:#211F1B;
    --border:#242320;
    --border-strong:#33312B;
    --text:#F0EADD; --text-2:#A49C8B; --text-3:#6E685B;
    --online:#8FBF9A;
    --radius:14px;
    --shadow:0 10px 34px rgba(0,0,0,.6);
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:var(--bg); color:var(--text);
    font-variant-numeric:tabular-nums;
    -webkit-font-smoothing:antialiased;
  }
  ::-webkit-scrollbar{width:9px;height:9px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border-strong);border-radius:20px;border:2px solid var(--bg)}
  ::-webkit-scrollbar-thumb:hover{background:var(--gold-700)}

  .app{display:flex;flex-direction:column;height:100dvh}

  /* Header */
  .header{
    display:flex;align-items:center;justify-content:space-between;
    padding:16px 24px;background:radial-gradient(70% 180% at 0% 50%, rgba(181,148,89,.07), transparent 42%), var(--surface-1);
    border-bottom:1px solid var(--border);position:relative;
  }
  .header::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:1px;
    background:linear-gradient(90deg,transparent,rgba(181,148,89,.5),transparent)}
  .brand{display:flex;align-items:center;gap:16px}
  .logo{height:48px;width:auto;display:block}
  .hdivider{width:1px;height:30px;background:var(--border-strong);flex-shrink:0}
  .mark{width:30px;height:30px;flex-shrink:0}
  .brand-text{display:flex;flex-direction:column;gap:2px;line-height:1}
  .wordmark{
    font-size:16px;font-weight:700;letter-spacing:.22em;
    background:var(--gold-grad);-webkit-background-clip:text;background-clip:text;color:transparent;
  }
  .subtitle{font-size:11px;color:var(--text-3);letter-spacing:.08em;text-transform:uppercase}
  .status{
    display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:500;
    color:var(--text-2);background:var(--surface-2);border:1px solid var(--border);
    padding:6px 12px;border-radius:20px;transition:color .2s,background .2s,border-color .2s;
  }
  .status .dot{width:7px;height:7px;border-radius:50%;background:var(--online);box-shadow:0 0 8px rgba(143,191,154,.6)}
  .status.alert{color:#1a1610;background:var(--gold-grad);border-color:transparent;font-weight:600}
  .status.alert .dot{background:#1a1610;box-shadow:none}

  .container{display:flex;flex:1;min-height:0}

  /* Sidebar */
  .sidebar{width:380px;flex-shrink:0;display:flex;flex-direction:column;
    background:var(--surface-1);border-right:1px solid var(--border)}
  .sidebar-top{padding:14px 16px;border-bottom:1px solid var(--border)}
  .search-wrap{position:relative;display:flex;align-items:center}
  .search-wrap svg{position:absolute;left:12px;width:16px;height:16px;color:var(--text-3);pointer-events:none}
  .search-box{
    width:100%;background:var(--surface-2);border:1px solid var(--border);border-radius:10px;
    padding:10px 12px 10px 36px;color:var(--text);font-size:13.5px;font-family:inherit;outline:none;
    transition:border-color .18s,box-shadow .18s;
  }
  .search-box::placeholder{color:var(--text-3)}
  .search-box:focus{border-color:var(--gold-500);box-shadow:0 0 0 3px rgba(181,148,89,.15)}
  .list-title{display:flex;justify-content:space-between;align-items:center;
    padding:14px 18px 8px;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold-700);font-weight:600}
  .total-badge{background:var(--surface-3);color:var(--text-2);padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600}
  .sidebar-list{flex:1;overflow-y:auto}
  .filter-tabs{display:flex;gap:6px;padding:0 18px 10px}
  .ftab{font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:4px 12px;border-radius:12px;
    border:1px solid var(--border);color:var(--text-2);cursor:pointer;background:none;font-weight:600;transition:.16s}
  .ftab:hover{color:var(--gold-300)}
  .ftab.active{border-color:var(--gold-500);color:var(--gold-300);background:rgba(181,148,89,.1)}
  .chip{display:inline-block;font-size:9px;letter-spacing:.1em;text-transform:uppercase;font-weight:700;
    padding:2px 7px;border-radius:9px;margin-left:8px;vertical-align:2px;flex-shrink:0}
  .chip-site{color:var(--gold-300);border:1px solid rgba(181,148,89,.55);background:rgba(181,148,89,.1)}
  .chip-zap{color:#7dc98f;border:1px solid rgba(37,211,102,.4);background:rgba(37,211,102,.08)}
  .avatar.ch-site{border-color:rgba(181,148,89,.6)}
  .avatar.ch-zap{border-color:rgba(37,211,102,.35)}

  .conv-item{
    display:flex;gap:13px;align-items:center;padding:13px 16px 13px 18px;
    border-bottom:1px solid var(--border);cursor:pointer;position:relative;
    border-left:3px solid transparent;transition:background .16s,border-color .16s;
  }
  .conv-item:hover{background:var(--surface-2)}
  .conv-item.active{background:linear-gradient(90deg,rgba(181,148,89,.13),rgba(181,148,89,0) 58%),var(--surface-2);border-left-color:var(--gold-500)}
  .conv-item.has-new{border-left-color:var(--gold-500)}
  .avatar{
    width:42px;height:42px;flex-shrink:0;border-radius:50%;display:flex;align-items:center;justify-content:center;
    background:var(--surface-3);border:1px solid var(--border-strong);
    color:var(--gold-300);font-weight:600;font-size:14px;letter-spacing:.02em;
  }
  .conv-item.has-new .avatar{border-color:var(--gold-500)}
  .conv-main{flex:1;min-width:0}
  .conv-top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
  .conv-name{font-weight:600;font-size:14.5px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .conv-item.has-new .conv-name{color:#fff}
  .conv-date{font-size:11px;color:var(--text-3);flex-shrink:0;white-space:nowrap}
  .conv-item.has-new .conv-date{color:var(--gold-300)}
  .conv-bottom{display:flex;justify-content:space-between;align-items:center;margin-top:3px;gap:10px}
  .conv-phone{font-size:12px;color:var(--text-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .conv-count{font-size:11.5px;color:var(--text-3);flex-shrink:0}
  .conv-badge{display:none;min-width:20px;height:20px;line-height:20px;padding:0 6px;border-radius:10px;
    background:var(--gold-grad);color:#181410;font-size:11px;font-weight:700;text-align:center;flex-shrink:0}
  .conv-item.has-new .conv-badge{display:inline-block}
  .conv-item.has-new .conv-count{display:none}

  .no-results{padding:36px 18px;text-align:center;color:var(--text-3);font-size:13px}

  /* Chat */
  .chat-area{flex:1;display:flex;flex-direction:column;background:var(--bg);min-width:0}
  .empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:14px;padding:24px;text-align:center}
  .empty svg{width:52px;height:52px;color:var(--gold-700);opacity:.7}
  .empty-text{font-size:14.5px;color:var(--text-2)}
  .empty-slogan{font-size:12.5px;color:var(--gold-700);font-style:italic;letter-spacing:.02em}

  .chat-header{display:flex;align-items:center;gap:13px;padding:13px 22px;
    background:var(--surface-1);border-bottom:1px solid var(--border)}
  .chat-back{display:none;background:none;border:none;color:var(--gold-300);cursor:pointer;
    padding:4px;border-radius:8px;transition:background .16s}
  .chat-back:hover{background:var(--surface-3)}
  .chat-back svg{width:22px;height:22px;display:block}
  .chat-header .avatar{width:38px;height:38px;font-size:13px}
  .chat-header-info h2{font-size:15px;font-weight:600;color:var(--text)}
  .chat-header-info .phone{font-size:12px;color:var(--text-3);margin-top:1px}

  .chat-messages{flex:1;overflow-y:auto;padding:22px 26px;display:flex;flex-direction:column;gap:7px}
  .date-sep{align-self:center;margin:14px 0 8px;display:flex;align-items:center;gap:12px;width:100%;max-width:420px}
  .date-sep::before,.date-sep::after{content:"";height:1px;flex:1;background:var(--border)}
  .date-sep span{font-size:11px;color:var(--text-3);letter-spacing:.04em;white-space:nowrap}

  .msg-row{display:flex;flex-direction:column;max-width:76%;gap:3px}
  .msg-row.patient{align-self:flex-end;align-items:flex-end}
  .msg-row.bot{align-self:flex-start;align-items:flex-start}
  .msg-sender{font-size:11px;font-weight:600;padding:0 4px;letter-spacing:.02em}
  .msg-row.patient .msg-sender{color:var(--text-2)}
  .msg-row.bot .msg-sender{color:var(--gold-500);text-transform:uppercase;letter-spacing:.08em}
  .msg-bubble{padding:11px 15px;font-size:14px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
  .msg-row.patient .msg-bubble{background:var(--surface-2);color:var(--cream);
    border:1px solid var(--border);border-radius:var(--radius);border-bottom-right-radius:5px}
  .msg-row.bot .msg-bubble{background:rgba(181,148,89,.11);color:var(--cream);
    border:1px solid rgba(181,148,89,.28);border-left:3px solid var(--gold-500);
    border-radius:var(--radius);border-bottom-left-radius:5px}
  .msg-time{font-size:10.5px;color:var(--text-3);padding:0 4px}

  @media (max-width:760px){
    .sidebar{width:100%}
    .chat-area{display:none}
    .container.chat-open .sidebar{display:none}
    .container.chat-open .chat-area{display:flex}
    .container.chat-open .chat-back{display:block}
    .msg-row{max-width:88%}
    .header{padding:14px 18px}
  }
  @media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="brand">
      <img class="logo" src="data:image/png;base64,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" alt="APEX CAPILAR" width="88" height="48">
      <span class="hdivider"></span>
      <span class="subtitle">Painel de Conversas</span>
    </div>
    <span class="status" id="statusBadge"><span class="dot"></span>Bot activo</span>
  </div>
  <div class="container" id="container">
    <div class="sidebar">
      <div class="sidebar-top">
        <div class="search-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <input class="search-box" id="searchInput" type="text" placeholder="Pesquisar por nome ou numero" oninput="filterConversations()">
        </div>
      </div>
      <div class="list-title"><span>Conversas</span><span class="total-badge" id="totalBadge">0</span></div>
      <div class="filter-tabs">
        <button class="ftab active" data-ch="all" onclick="setChannel('all')">Todas</button>
        <button class="ftab" data-ch="zap" onclick="setChannel('zap')">WhatsApp</button>
        <button class="ftab" data-ch="site" onclick="setChannel('site')">Site</button>
      </div>
      <div class="sidebar-list"><div id="sidebar"></div></div>
    </div>
    <div class="chat-area" id="chatArea">
      <div class="empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <div class="empty-text">Selecione uma conversa para visualizar</div>
        <div class="empty-slogan">Sua confianca, no ponto mais alto.</div>
      </div>
    </div>
  </div>
</div>
<script>
const TOKEN = new URLSearchParams(location.search).get('token') || '';
const API = (path) => path + '?token=' + encodeURIComponent(TOKEN);
let allConvs = [];
let currentPhone = null;
let seenCounts = JSON.parse(localStorage.getItem('apex_seen') || '{}');

function saveSeen(){ localStorage.setItem('apex_seen', JSON.stringify(seenCounts)); }
function getNewCount(phone,total){ const s = seenCounts[phone] || 0; return Math.max(0, total - s); }
function markSeen(phone,total){ seenCounts[phone] = total; saveSeen(); }
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function channelOf(phone){ return String(phone||'').startsWith('web:') ? 'site' : 'zap'; }
function sidShort(phone){ return String(phone).slice(4, 10); }
function displayName(c){
  if(channelOf(c.phone) === 'site') return 'Visitante do site \u00b7 ' + sidShort(c.phone);
  return c.name || 'Sem nome';
}
function displayId(phone){
  return channelOf(phone) === 'site' ? ('Sess\u00e3o web \u00b7 ' + sidShort(phone)) : ('+' + phone);
}
function chipHtml(phone){
  return channelOf(phone) === 'site'
    ? '<span class="chip chip-site">Site</span>'
    : '<span class="chip chip-zap">WhatsApp</span>';
}
function initials(name){
  const parts = (name||'').trim().split(' ').filter(Boolean);
  if(!parts.length) return '?';
  const a = parts[0][0] || '';
  const b = parts.length>1 ? parts[parts.length-1][0] : '';
  return (a+b).toUpperCase();
}
function formatDate(iso){
  const d = new Date(iso), now = new Date();
  const diff = (now - d) / 86400000;
  if(diff < 1 && d.getDate() === now.getDate()) return 'Hoje';
  if(diff < 2) return 'Ontem';
  return d.toLocaleDateString('pt-PT',{day:'2-digit',month:'short',year:'numeric'});
}
function formatTime(iso){
  return new Date(iso).toLocaleString('pt-PT',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
}

function renderConversations(convs){
  const sb = document.getElementById('sidebar');
  if(!convs.length){ sb.innerHTML = '<div class="no-results">Nenhuma conversa encontrada</div>'; return; }
  sb.innerHTML = convs.map(c => {
    const nw = getNewCount(c.phone, c.total_messages);
    const cls = nw > 0 ? ' has-new' : '';
    const active = c.phone === currentPhone ? ' active' : '';
    const ch = channelOf(c.phone);
    const name = esc(displayName(c));
    return `<div class="conv-item${cls}${active}" data-phone="${c.phone}" data-name="${name}" data-total="${c.total_messages}">
      <div class="avatar ch-${ch}">${ch === 'site' ? 'VS' : esc(initials(c.name))}</div>
      <div class="conv-main">
        <div class="conv-top"><span class="conv-name">${name}${chipHtml(c.phone)}</span><span class="conv-date">${formatDate(c.last_message)}</span></div>
        <div class="conv-bottom">
          <span class="conv-phone">${esc(displayId(c.phone))}</span>
          <span class="conv-count">${c.total_messages} mensagens</span>
          <span class="conv-badge">${nw}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

let channelFilter = 'all';
function setChannel(ch){
  channelFilter = ch;
  document.querySelectorAll('.ftab').forEach(b => b.classList.toggle('active', b.dataset.ch === ch));
  filterConversations();
}
function filterConversations(){
  const q = document.getElementById('searchInput').value.toLowerCase().trim();
  let list = allConvs;
  if(channelFilter !== 'all') list = list.filter(c => channelOf(c.phone) === channelFilter);
  if(q) list = list.filter(c =>
    (c.name||'').toLowerCase().includes(q) || (c.phone||'').toLowerCase().includes(q));
  renderConversations(list);
}

async function load(){
  try{
    const res = await fetch(API('/api/conversations'));
    if(!res.ok){ document.getElementById('sidebar').innerHTML = '<div class="no-results">Acesso negado</div>'; return; }
    allConvs = await res.json();
    document.getElementById('totalBadge').textContent = allConvs.length;

    const totalNew = allConvs.reduce((s,c) => s + getNewCount(c.phone, c.total_messages), 0);
    const badge = document.getElementById('statusBadge');
    if(totalNew > 0){
      badge.className = 'status alert';
      badge.innerHTML = '<span class="dot"></span>' + totalNew + (totalNew > 1 ? ' novas' : ' nova');
      document.title = '(' + totalNew + ') APEX CAPILAR — Conversas';
    } else {
      badge.className = 'status';
      badge.innerHTML = '<span class="dot"></span>Bot activo';
      document.title = 'APEX CAPILAR — Conversas';
    }
    filterConversations();
    if(currentPhone) refreshChat();
  } catch(e){ console.error(e); }
}

async function refreshChat(){
  if(!currentPhone) return;
  const res = await fetch(API('/api/conversations/' + currentPhone));
  const msgs = await res.json();
  const box = document.querySelector('.chat-messages');
  if(!box) return;
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 60;
  renderMessages(box, msgs);
  if(atBottom) box.scrollTop = box.scrollHeight;
  const conv = allConvs.find(c => c.phone === currentPhone);
  if(conv) markSeen(currentPhone, conv.total_messages);
}

function renderMessages(container, msgs){
  let lastDate = '', html = '';
  msgs.forEach(m => {
    const md = formatDate(m.created_at);
    if(md !== lastDate){ html += `<div class="date-sep"><span>${md}</span></div>`; lastDate = md; }
    const patient = m.role === 'user';
    const cls = patient ? 'patient' : 'bot';
    const sender = patient ? esc(m.name || 'Paciente') : 'APEX CAPILAR';
    html += `<div class="msg-row ${cls}">
      <div class="msg-sender">${sender}</div>
      <div class="msg-bubble">${esc(m.content)}</div>
      <div class="msg-time">${formatTime(m.created_at)}</div>
    </div>`;
  });
  container.innerHTML = html;
}

async function openChat(phone, name){
  currentPhone = phone;
  document.getElementById('container').classList.add('chat-open');
  const res = await fetch(API('/api/conversations/' + phone));
  const msgs = await res.json();
  const ca = document.getElementById('chatArea');
  ca.innerHTML = `
    <div class="chat-header">
      <button class="chat-back" aria-label="Voltar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="avatar ch-${channelOf(phone)}">${channelOf(phone) === 'site' ? 'VS' : esc(initials(name))}</div>
      <div class="chat-header-info"><h2>${esc(name || 'Paciente')}${chipHtml(phone)}</h2><div class="phone">${esc(displayId(phone))}</div></div>
    </div>
    <div class="chat-messages"></div>`;
  renderMessages(ca.querySelector('.chat-messages'), msgs);
  ca.querySelector('.chat-messages').scrollTop = 999999;
  const conv = allConvs.find(c => c.phone === phone);
  markSeen(phone, conv ? conv.total_messages : 0);
  load();
}

document.getElementById('sidebar').addEventListener('click', (e) => {
  const item = e.target.closest('.conv-item');
  if(!item) return;
  openChat(item.dataset.phone, item.dataset.name);
});
document.getElementById('chatArea').addEventListener('click', (e) => {
  if(e.target.closest('.chat-back')){
    currentPhone = null;
    document.getElementById('container').classList.remove('chat-open');
    load();
  }
});

load();
setInterval(load, 15000);
</script>
</body>
</html>
"""

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
