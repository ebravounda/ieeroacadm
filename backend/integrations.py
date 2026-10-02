import secrets
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from core import db, get_cfg, send_email, analyze_ai_usage, _brand, logger
from server import admin_only, app_base

router = APIRouter()
SECRET_FIELDS = ["resend_api_key", "openai_api_key"]
CRON_JOBS = [("*/15 * * * *", "class-reminders", "Recordatorio de clases (cada 15 min)"),
             ("0 10 * * *", "inactivity-alerts", "Alertas de inactividad (diario 10:00)"),
             ("0 8 * * 1", "weekly-report", "Reporte semanal OTEC (lunes 08:00)")]


def _hint(v: str) -> str:
    return f"••••{v[-4:]}" if v else ""


async def _view(request: Request):
    c = await get_cfg()
    base = app_base(request)
    pay = await db.settings.find_one({"id": "payments"}, {"_id": 0}) or {}
    cron = [{"label": label, "line": f"{exp} curl -s -X POST {base}/api/cron/{path} -H \"Authorization: Bearer {c['cron_secret']}\" "
             "-H \"Content-Type: application/json\" -d '{}'"} for exp, path, label in CRON_JOBS]
    return {
        "email": {"active": bool(c["resend_api_key"] and c["mail_from"]), "key_hint": _hint(c["resend_api_key"]),
                  "mail_from": c["mail_from"], "email_from_name": c["email_from_name"]},
        "ai": {"active": bool(c["openai_api_key"]), "key_hint": _hint(c["openai_api_key"]), "openai_model": c["openai_model"]},
        "payments": {"active": bool(pay.get("flow_api_key") and pay.get("flow_secret_key")), "flow_env": pay.get("flow_env", "sandbox")},
        "cron": {"active": bool(c["cron_secret"]), "secret_hint": _hint(c["cron_secret"]), "lines": cron if c["cron_secret"] else []},
    }


class IntegrationsIn(BaseModel):
    resend_api_key: Optional[str] = None
    mail_from: Optional[str] = None
    email_from_name: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    clear: List[str] = []


@router.get("/admin/integrations")
async def get_integrations(request: Request, _=Depends(admin_only)):
    return await _view(request)


@router.put("/admin/integrations")
async def put_integrations(body: IntegrationsIn, request: Request, _=Depends(admin_only)):
    upd = {k: v.strip() for k, v in body.model_dump(exclude={"clear"}).items() if v is not None and (v.strip() or k not in SECRET_FIELDS)}
    if upd.get("mail_from") and "@" not in upd["mail_from"]:
        raise HTTPException(400, "Correo remitente inválido")
    unset = {k: "" for k in body.clear if k in SECRET_FIELDS}
    op = {"$set": upd} if upd else {}
    if unset:
        op["$unset"] = unset
    if op:
        await db.settings.update_one({"id": "integrations"}, op, upsert=True)
    return await _view(request)


class TestEmailIn(BaseModel):
    to: EmailStr


@router.post("/admin/integrations/test-email")
async def test_email(body: TestEmailIn, _=Depends(admin_only)):
    html = (f'<div style="font-family:Arial,sans-serif;padding:24px">{_brand()}'
            '<p>Este es un correo de prueba. La integración de correo de la plataforma funciona correctamente.</p></div>')
    await send_email(to=body.to, subject="Correo de prueba · IberoAcademy", html=html)
    return {"ok": True}


@router.post("/admin/integrations/test-ai")
async def test_ai(_=Depends(admin_only)):
    try:
        r = await analyze_ai_usage([{"id": "q1", "type": "open", "text": "¿Qué es una OTEC?"}],
                                   {"q1": "Es un organismo técnico de capacitación."}, {})
    except httpx.HTTPStatusError as e:
        logger.error(f"AI test failed: {e.response.status_code} {e.response.text[:300]}")
        raise HTTPException(502, f"OpenAI rechazó la solicitud ({e.response.status_code}). Revisa la clave y el modelo.")
    except Exception as e:
        logger.error(f"AI test error: {e}")
        raise HTTPException(502, "No se pudo conectar con el servicio de IA")
    return {"ok": True, "percentage": r.get("percentage"), "level": r.get("level")}


@router.post("/admin/integrations/cron-secret")
async def regen_cron_secret(request: Request, _=Depends(admin_only)):
    await db.settings.update_one({"id": "integrations"}, {"$set": {"cron_secret": secrets.token_urlsafe(32)}}, upsert=True)
    return await _view(request)
