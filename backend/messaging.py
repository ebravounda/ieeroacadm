import asyncio
import re
from datetime import timedelta
from html import escape
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

import core
from core import db, now, now_iso, new_id, send_email, _brand, logger, EMAIL_FROM_NAME
from server import admin_only

router = APIRouter()

DEFAULTS = [
    ("Bienvenida", "¡Bienvenido(a) a IberoAcademy, {nombre}!",
     "Hola {nombre},\n\nTe damos la más cordial bienvenida a IberoAcademy. Ya puedes ingresar a la plataforma con tu correo {email}; "
     "te enviaremos un código de acceso cada vez que entres.\n\nTe recomendamos dedicar tiempo de calidad a cada módulo, revisar todos "
     "los materiales y rendir el examen al finalizar cada uno.\n\n[Ingresar a la plataforma]({enlace})\n\n¡Mucho éxito!"),
    ("Recordatorio de avance", "{nombre}, tu curso te espera",
     "Hola {nombre},\n\nTe recordamos continuar con tu curso {curso}. Avanzar con constancia es la clave para terminarlo a tiempo "
     "y obtener tu certificado.\n\nRecuerda que la plataforma registra tus ingresos y el tiempo dedicado a cada módulo.\n\n"
     "[Continuar mi curso]({enlace})"),
    ("Nuevo curso disponible", "Nuevo curso disponible en IberoAcademy",
     "Hola {nombre},\n\nTenemos un nuevo curso disponible que puede interesarte: [nombre del curso].\n\n"
     "Revisa los detalles, horarios y valores en nuestro sitio.\n\n[Ver cursos]({enlace})"),
    ("Aviso general", "Información importante – IberoAcademy",
     "Hola {nombre},\n\n[Escribe aquí tu aviso]\n\nAnte cualquier duda, responde a este correo.\n\nSaludos cordiales,\nEquipo IberoAcademy"),
]
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_URL = re.compile(r"(?<![\"'>])(https?://[^\s<]+)")


def render_body(text: str) -> str:
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        h = escape(para)
        links = []
        def keep(m):
            links.append(f'<a href="{m.group(2)}" style="color:#11305c;font-weight:bold">{m.group(1)}</a>')
            return f"\x00{len(links) - 1}\x00"
        h = _LINK.sub(keep, h)
        h = _URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:#11305c">{m.group(1)}</a>', h)
        h = re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], h).replace("\n", "<br>")
        out.append(f'<p style="margin:0 0 14px">{h}</p>')
    return ('<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a;line-height:1.55">'
            f'{_brand()}{"".join(out)}<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}.</p></td></tr></table>')


def fill(text: str, v: dict) -> str:
    for k, val in v.items():
        text = text.replace("{" + k + "}", val)
    return text


def link() -> str:
    return f"{core.PUBLIC_BASE}/login" if core.PUBLIC_BASE.startswith("https://") else ""


class Audience(BaseModel):
    type: str = "students"
    course_id: Optional[str] = None
    days: int = 7


async def recipients(a: Audience) -> list:
    q = {"active": True}
    course_title = ""
    if a.type == "students":
        q["role"] = "estudiante"
    elif a.type == "course":
        c = await db.courses.find_one({"id": a.course_id}, {"_id": 0, "title": 1})
        if not c:
            raise HTTPException(400, "Selecciona un curso")
        course_title = c["title"]
        ids = [e["user_id"] async for e in db.enrollments.find({"course_id": a.course_id}, {"user_id": 1})]
        q["id"] = {"$in": ids}
    elif a.type == "inactive":
        cut = (now() - timedelta(days=max(1, a.days))).isoformat()
        q.update({"role": "estudiante", "$or": [{"last_login": None}, {"last_login": {"$lt": cut}}]})
    elif a.type != "all":
        raise HTTPException(400, "Destinatarios inválidos")
    users = await db.users.find(q, {"_id": 0, "id": 1, "email": 1, "nombre": 1, "apellidos": 1}).to_list(20000)
    titles = {c["id"]: c["title"] async for c in db.courses.find({}, {"_id": 0, "id": 1, "title": 1})}
    for u in users:
        if course_title:
            u["curso"] = course_title
        else:
            e = await db.enrollments.find_one({"user_id": u["id"]}, {"course_id": 1}, sort=[("enrolled_at", -1)])
            u["curso"] = titles.get(e["course_id"], "") if e else ""
    return users


def vars_for(u: dict) -> dict:
    return {"nombre": u.get("nombre") or "", "apellidos": u.get("apellidos") or "", "email": u["email"],
            "curso": u.get("curso") or "tu curso", "enlace": link()}


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)


@router.get("/admin/templates")
async def list_templates(_=Depends(admin_only)):
    if not await db.app_meta.find_one({"id": "templates_seeded"}):
        await db.email_templates.insert_many([{"id": new_id(), "name": n, "subject": s, "body": b, "created_at": now_iso()}
                                              for n, s, b in DEFAULTS])
        await db.app_meta.insert_one({"id": "templates_seeded"})
    return await db.email_templates.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)


@router.post("/admin/templates")
async def create_template(body: TemplateIn, _=Depends(admin_only)):
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.email_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/admin/templates/{tid}")
async def update_template(tid: str, body: TemplateIn, _=Depends(admin_only)):
    r = await db.email_templates.update_one({"id": tid}, {"$set": body.model_dump()})
    if not r.matched_count:
        raise HTTPException(404, "Plantilla no encontrada")
    return {"id": tid, **body.model_dump()}


@router.delete("/admin/templates/{tid}")
async def delete_template(tid: str, _=Depends(admin_only)):
    await db.email_templates.delete_one({"id": tid})
    return {"ok": True}


class MessageIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    audience: Audience = Audience()


class TestIn(MessageIn):
    to: EmailStr


def _build(m: MessageIn, v: dict):
    subject, html = fill(m.subject, v), render_body(fill(m.body, v))
    try:
        core._assert_safe_email(subject, html)
    except ValueError as e:
        raise HTTPException(400, f"El mensaje tiene un enlace no permitido: {e}")
    return subject, html


@router.post("/admin/messages/preview")
async def preview(m: MessageIn, _=Depends(admin_only)):
    users = await recipients(m.audience)
    sample = users[0] if users else {"email": "alumno@correo.cl", "nombre": "María", "apellidos": "Pérez", "curso": "Nombre del curso"}
    subject, html = _build(m, vars_for(sample))
    return {"count": len(users), "subject": subject, "html": html}


@router.post("/admin/messages/test")
async def send_test(m: TestIn, admin=Depends(admin_only)):
    subject, html = _build(m, vars_for({"email": m.to, "nombre": admin.get("nombre") or "", "curso": "Nombre del curso"}))
    await send_email(to=m.to, subject=f"[Prueba] {subject}", html=html)
    return {"ok": True}


async def run_campaign(cid: str, m: MessageIn, users: list):
    sent = failed = 0
    for u in users:
        try:
            subject, html = _build(m, vars_for(u))
            await send_email(to=u["email"], subject=subject, html=html)
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Campaign {cid} to {u['email']} failed: {e}")
        if (sent + failed) % 10 == 0:
            await db.campaigns.update_one({"id": cid}, {"$set": {"sent": sent, "failed": failed}})
        await asyncio.sleep(0.6)
    await db.campaigns.update_one({"id": cid}, {"$set": {"sent": sent, "failed": failed, "status": "completado",
                                                         "finished_at": now_iso()}})


@router.post("/admin/messages/send")
async def send_campaign(m: MessageIn, admin=Depends(admin_only)):
    users = await recipients(m.audience)
    if not users:
        raise HTTPException(400, "No hay destinatarios para esta selección")
    _build(m, vars_for(users[0]))
    doc = {"id": new_id(), "subject": m.subject, "audience": m.audience.model_dump(), "total": len(users), "sent": 0,
           "failed": 0, "status": "enviando", "created_at": now_iso(), "by": admin["email"]}
    await db.campaigns.insert_one(doc)
    asyncio.create_task(run_campaign(doc["id"], m, users))
    doc.pop("_id", None)
    return doc


@router.get("/admin/messages/campaigns")
async def list_campaigns(_=Depends(admin_only)):
    return await db.campaigns.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
