import os
import re
import json
import uuid
import ipaddress
import logging
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import jwt
import httpx
import requests
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger("otec")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

JWT_ALGORITHM = "HS256"
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ["EMERGENT_EMAIL_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
PUBLIC_BASE = ""


def _brand() -> str:
    if PUBLIC_BASE.startswith("https://"):
        return (f'<img src="{escape(PUBLIC_BASE)}/logo.png" alt="{escape(EMAIL_FROM_NAME)}" width="140" '
                'style="display:block;margin:0 0 16px;border:0">')
    return f'<h2 style="margin:0 0 12px">{escape(EMAIL_FROM_NAME)}</h2>'


def now():
    return datetime.now(timezone.utc)


def now_iso():
    return now().isoformat()


def new_id():
    return str(uuid.uuid4())


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": now() + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def create_file_token(file_id: str) -> str:
    payload = {"sub": file_id, "exp": now() + timedelta(hours=2), "type": "file"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def read_file_token(token: str):
    try:
        p = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    return p["sub"] if p.get("type") == "file" else None


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token") or request.query_params.get("auth")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "No autenticado")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")
    if payload.get("type") != "access":
        raise HTTPException(401, "Token inválido")
    user = await db.users.find_one({"id": payload["sub"], "active": True}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    return user


def require_roles(*roles):
    async def dep(request: Request):
        user = await get_current_user(request)
        if user["role"] not in roles:
            raise HTTPException(403, "Sin permisos")
        return user
    return dep


# ---------- Email (Emergent managed Resend) ----------
_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str):
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise HTTPException(502, "No se pudo enviar el correo")
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise HTTPException(500, "No se pudo enviar el correo")


def otp_email_html(name: str, code: str) -> str:
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}'
        f'<p>Hola {escape(name)}, este es tu código para ingresar a la plataforma:</p>'
        f'<p style="font-size:32px;letter-spacing:8px;font-weight:bold;color:#0d9488">{escape(code)}</p>'
        '<p>El código vence en 10 minutos. Si no solicitaste este ingreso, ignora este mensaje.</p>'
        f'<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}. Nunca te pediremos este código por correo ni teléfono.</p>'
        '</td></tr></table>'
    )


def class_reminder_html(name, title, course, hora, platform) -> str:
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}'
        f'<p>Hola {escape(name)}, te recordamos que tu clase en vivo está por comenzar.</p>'
        f'<p style="font-size:20px;font-weight:bold;margin:8px 0">{escape(title)}</p>'
        f'<p>Curso: {escape(course)}<br>Hora de inicio: <b>{escape(hora)} (hora de Chile)</b><br>Plataforma: {escape(platform)}</p>'
        '<p>Ingresa a la plataforma y usa el botón “Abrir clase” en la sección Clases en vivo para unirte y registrar tu asistencia.</p>'
        f'<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


def inactivity_email_html(name, days, course, progress, next_step) -> str:
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}'
        f'<p>Hola {escape(name)}, hace {days} días que no ingresas a la plataforma. ¡Tu curso te espera!</p>'
        f'<p style="font-size:18px;font-weight:bold;margin:8px 0">{escape(course)}</p>'
        f'<p>Llevas un <b>{progress}%</b> de avance.</p>'
        f'<p style="background:#f0fdfa;border-left:4px solid #0d9488;padding:12px">Tu siguiente paso: <b>{escape(next_step)}</b></p>'
        '<p>Ingresa a la plataforma y revisa la sección “Mi avance” para continuar donde quedaste. ¡Tú puedes!</p>'
        f'<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


def cert_request_email_html(admin_name, student, course, nota) -> str:
    nota_txt = f" con nota final <b>{nota:.1f}</b>".replace(".", ",") if nota else ""
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}'
        f'<p>Hola {escape(admin_name)}, hay una nueva <b>solicitud de aprobación de certificado</b>.</p>'
        f'<p style="font-size:16px"><b>{escape(student)}</b> finalizó el curso <b>{escape(course)}</b>{nota_txt}.</p>'
        '<p>Ingresa a la plataforma, sección <b>Diplomas</b>, para revisar y aprobar la emisión del certificado.</p>'
        f'<p style="font-size:12px;color:#888">Enviado automáticamente por {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


def cert_approved_email_html(name, course, nota, code, verify_url, phrase) -> str:
    nota_txt = f"<p>Tu nota final: <b>{nota:.1f}</b></p>".replace(".", ",", 1) if nota else ""
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}'
        f'<p style="font-size:22px;font-weight:bold;color:#0d9488;margin:8px 0">¡Felicidades, {escape(name)}!</p>'
        f'<p>Has completado tu curso <b>{escape(course)}</b> exitosamente. Tu certificado fue aprobado y ya está disponible.</p>'
        f'{nota_txt}'
        f'<p style="background:#f0fdfa;border-left:4px solid #0d9488;padding:12px;font-style:italic">“{escape(phrase)}”</p>'
        f'<p>Código de aprobación: <b style="font-family:monospace">{escape(code)}</b></p>'
        f'<p><a href="{escape(verify_url)}" style="display:inline-block;background:#0d9488;color:#fff;padding:12px 20px;'
        'border-radius:8px;text-decoration:none;font-weight:bold">Descargar mi certificado (PDF)</a></p>'
        '<p style="font-size:13px;color:#475569">También puedes descargarlo cuando quieras en la sección Diplomas de la plataforma.</p>'
        f'<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


def weekly_report_html(reports, date) -> str:
    def n(v):
        return "—" if v is None else f"{v:.1f}".replace(".", ",")
    th = 'style="text-align:left;padding:6px 8px;background:#0f172a;color:#fff;font-size:12px"'
    td = 'style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:12px"'
    parts = []
    for r in reports:
        c, s = r["course"], r["summary"]
        rows = "".join(
            f'<tr><td {td}>{escape(x["student_name"])}<br><span style="color:#64748b">{escape(x["rut"] or x["email"])}</span></td>'
            f'<td {td}>{x["days_attended"]}</td><td {td}>{x["total_minutes"]} min</td>'
            f'<td {td}>{x["live_attended"]}/{x["live_total"]}</td><td {td}>{x["modules_done"]}/{x["modules_total"]}</td>'
            f'<td {td}>{n(x["modules_avg_nota"])}</td><td {td}>{n(x["final_nota"])}</td>'
            f'<td {td}><b>{n(x["overall_nota"])}</b></td><td {td}>{escape(x["status"])}</td></tr>'
            for x in r["rows"]) or f'<tr><td {td} colspan="9">Sin estudiantes matriculados.</td></tr>'
        heads = "".join(f"<th {th}>{h}</th>" for h in ("Estudiante", "Días curso", "Permanencia", "Clases", "Módulos",
                                                        "Prom. mód.", "Ex. final", "Nota final", "Estado"))
        parts.append(
            f'<h3 style="margin:24px 0 4px">{escape(c["title"])} <span style="color:#64748b;font-weight:normal">{escape(c["code"] or "")}</span></h3>'
            f'<p style="margin:0 0 8px;color:#475569;font-size:13px">{s["students"]} matriculados · {s["approved"]} aprobados · {s["live_classes"]} clases en vivo · {c["hours"]} horas</p>'
            f'<table role="presentation" cellspacing="0" style="border-collapse:collapse;width:100%"><tr>{heads}</tr>{rows}</table>')
    body = "".join(parts) or "<p>No hay cursos registrados.</p>"
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}<h2 style="margin:0 0 4px">Reporte semanal OTEC</h2>'
        f'<p style="margin:0;color:#475569">Corte al {escape(date)}. Notas en escala 1,0 – 7,0. Permanencia medida dentro de cada curso.</p>'
        f'{body}'
        '<p style="margin-top:24px;font-size:13px">Para descargar el detalle completo en CSV, ingresa a Cursos y módulos → curso → pestaña “Reporte OTEC”.</p>'
        f'<p style="font-size:12px;color:#888">Enviado automáticamente cada lunes por {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


def grade_email_html(name, course, exam, nota, score, passed, feedback) -> str:
    nota_txt = f"{nota:.1f}".replace(".", ",")
    color = "#059669" if passed else "#e11d48"
    fb = f'<p><b>Comentario del docente:</b> {escape(feedback)}</p>' if feedback else ""
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
        f'{_brand()}'
        f'<p>Hola {escape(name)}, tu docente calificó tu {escape(exam)} del curso <b>{escape(course)}</b>.</p>'
        f'<p style="font-size:36px;font-weight:bold;color:{color};margin:8px 0">Nota {nota_txt}</p>'
        f'<p>Logro: {score}% · {"Aprobado" if passed else "No aprobado"}</p>'
        f'{fb}'
        '<p>Ingresa a la plataforma para ver el detalle y continuar tu curso.</p>'
        f'<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>'
    )


# ---------- Object storage ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "iberoacademy"
_storage_key = None


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": init_storage(), "Content-Type": content_type},
                        data=data, timeout=300)
    if resp.status_code == 404:
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": init_storage(True), "Content-Type": content_type},
                            data=data, timeout=300)
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=120)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------- Chilean grades (1.0 - 7.0) ----------
def to_nota(pct, exigencia=60):
    if pct is None:
        return None
    e = max(1, min(99, exigencia))
    nota = 1 + 3 * pct / e if pct < e else 4 + 3 * (pct - e) / (100 - e)
    return round(max(1.0, min(7.0, nota)), 1)


# ---------- AI usage analysis (Claude) ----------
AI_SYSTEM = (
    "Eres un experto en detección de texto generado por inteligencia artificial en evaluaciones académicas. "
    "Analizas respuestas abiertas de estudiantes y estimas qué porcentaje del texto fue probablemente "
    "generado por IA (ChatGPT, Claude, Gemini, etc.). Consideras estilo, estructura excesivamente pulida, "
    "frases genéricas, vocabulario, coherencia con el nivel del estudiante y señales de comportamiento. "
    "Responde SOLO con JSON válido, sin markdown."
)


async def analyze_ai_usage(questions: list, answers: dict, behavior: dict) -> dict:
    items = []
    for q in questions:
        if q.get("type") == "open":
            items.append({"question_id": q["id"], "pregunta": q["text"], "respuesta": answers.get(q["id"], "")})
    if not items:
        return {"percentage": 0, "level": "bajo", "summary": "La evaluación no contiene respuestas abiertas para analizar.",
                "answers": []}
    prompt = (
        "Analiza estas respuestas de un examen. Señales de comportamiento durante el examen: "
        f"cambios de pestaña={behavior.get('tab_switches', 0)}, pegados de texto={behavior.get('paste_events', 0)}, "
        f"duración={behavior.get('duration_sec', 0)} segundos.\n\n"
        f"Respuestas:\n{json.dumps(items, ensure_ascii=False)}\n\n"
        'Devuelve JSON con este formato exacto: {"percentage": <0-100 entero global>, "level": "bajo|medio|alto", '
        '"summary": "<explicación breve en español>", "answers": [{"question_id": "...", "percentage": <0-100>, '
        '"reasoning": "<motivo breve en español>"}]}'
    )
    chat = LlmChat(api_key=LLM_KEY, session_id=new_id(), system_message=AI_SYSTEM).with_model(
        "anthropic", "claude-sonnet-5-5")
    raw = await chat.send_message(UserMessage(text=prompt))
    text = raw if isinstance(raw, str) else str(raw)
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0))
    data["percentage"] = max(0, min(100, int(data.get("percentage", 0))))
    return data
