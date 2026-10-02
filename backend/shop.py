import hashlib
import hmac
from html import escape
from typing import List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from core import db, now_iso, new_id, send_email, get_object, logger, EMAIL_FROM_NAME, _brand
import asyncio
from server import admin_only, staff_only, create_user, enroll, app_base

router = APIRouter()
FLOW_URLS = {"sandbox": "https://sandbox.flow.cl/api", "production": "https://www.flow.cl/api"}
STATUS = {1: "pendiente", 2: "pagado", 3: "rechazado", 4: "anulado"}


# ---------- Flow helpers ----------
async def flow_conf():
    s = await db.settings.find_one({"id": "payments"}, {"_id": 0}) or {}
    if not s.get("flow_api_key") or not s.get("flow_secret_key"):
        raise HTTPException(503, "Los pagos en línea aún no están configurados. Contacta a IberoAcademy.")
    return s


def signed(params: dict, secret: str) -> dict:
    to_sign = "".join(k + str(params[k]) for k in sorted(params))
    return {**params, "s": hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest()}


async def flow_call(method: str, path: str, params: dict):
    s = await flow_conf()
    url = FLOW_URLS.get(s.get("flow_env", "sandbox"), FLOW_URLS["sandbox"]) + path
    data = signed({"apiKey": s["flow_api_key"], **params}, s["flow_secret_key"])
    async with httpx.AsyncClient(timeout=20) as c:
        r = await (c.post(url, data=data) if method == "POST" else c.get(url, params=data))
    if r.status_code >= 400:
        logger.error(f"Flow {path} error {r.status_code}: {r.text[:300]}")
        raise HTTPException(400, "Flow rechazó la solicitud. Revisa las credenciales en Sitio web y pagos.")
    return r.json()


async def create_flow_link(pay: dict, base: str) -> str:
    res = await flow_call("POST", "/payment/create", {
        "commerceOrder": pay["order"], "subject": f"Curso {pay['course_title']}"[:120], "currency": "CLP",
        "amount": str(pay["amount"]), "email": pay["email"],
        "urlConfirmation": f"{base}/api/payments/flow/confirm", "urlReturn": f"{base}/api/payments/flow/return"})
    link = f"{res['url']}?token={res['token']}"
    await db.payments.update_one({"id": pay["id"]}, {"$set": {"flow_token": res["token"], "flow_order": res.get("flowOrder"),
                                                              "checkout_url": link, "base": base}})
    return link


def email_html(title: str, body: str, link: str = "", label: str = "") -> str:
    btn = (f'<p><a href="{escape(link)}" style="display:inline-block;background:#11305c;color:#fff;padding:12px 20px;'
           f'border-radius:8px;text-decoration:none;font-weight:bold">{escape(label)}</a></p>') if link else ""
    return ('<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#0f172a">'
            f'{_brand()}<p style="font-size:20px;font-weight:bold;color:#11305c">{escape(title)}</p>{body}{btn}'
            f'<p style="font-size:12px;color:#888">Enviado por {escape(EMAIL_FROM_NAME)}.</p></td></tr></table>')


async def grant_access(pay: dict, method: str):
    if pay.get("enrolled"):
        return
    await enroll(pay["user_id"], pay["course_id"], method)
    await db.payments.update_one({"id": pay["id"]}, {"$set": {"enrolled": True, "status": "pagado", "paid_at": now_iso()}})
    base = pay.get("base", "")
    try:
        await send_email(to=pay["email"], subject=f"Pago confirmado: {pay['course_title']} – {EMAIL_FROM_NAME}",
                         html=email_html(f"¡Bienvenido(a), {pay['student_name']}!",
                                         f"<p>Confirmamos tu pago de <b>${pay['amount']:,}</b> por el curso <b>{escape(pay['course_title'])}</b>."
                                         .replace(",", ".") + "</p><p>Ya puedes comenzar. Ingresa a la plataforma con tu correo; "
                                         "te enviaremos un código de acceso cada vez que entres.</p>",
                                         f"{base}/login" if base.startswith("https://") else "", "Ingresar a mi curso"))
    except Exception as ex:
        logger.error(f"Paid email failed: {ex}")


async def sync_payment(token: str):
    pay = await db.payments.find_one({"flow_token": token}, {"_id": 0})
    if not pay:
        raise HTTPException(404, "Pago no encontrado")
    st = await flow_call("GET", "/payment/getStatus", {"token": token})
    if str(st.get("commerceOrder")) != pay["order"]:
        raise HTTPException(400, "Orden no coincide")
    status = STATUS.get(int(st.get("status", 1)), "pendiente")
    if status == "pagado" and int(float(st.get("amount", 0))) >= pay["amount"]:
        await grant_access(pay, "pago")
    elif status != "pagado":
        await db.payments.update_one({"id": pay["id"]}, {"$set": {"status": status}})
    return await db.payments.find_one({"id": pay["id"]}, {"_id": 0})


async def new_payment(user: dict, course: dict) -> dict:
    pay = {"id": new_id(), "order": f"IBA-{new_id()[:8].upper()}", "user_id": user["id"], "email": user["email"],
           "student_name": f"{user['nombre']} {user['apellidos']}", "rut": user.get("rut", ""),
           "course_id": course["id"], "course_title": course["title"], "amount": int(course.get("price", 0)),
           "status": "pendiente", "enrolled": False, "created_at": now_iso()}
    await db.payments.insert_one(dict(pay))
    return pay


# ---------- Public landing ----------
def public_course(c):
    return {k: c.get(k) for k in ("id", "title", "summary", "description", "price", "hours", "code", "modality")} | {
        "image_url": f"/api/public/images/{c['image_file_id']}" if c.get("image_file_id") else None}


@router.get("/public/landing")
async def landing():
    s = await db.settings.find_one({"id": "landing"}, {"_id": 0}) or {}
    courses = await db.courses.find({"published": True, "show_on_landing": True}, {"_id": 0}).sort("created_at", -1).to_list(200)
    slides = [{**x, "image_url": f"/api/public/images/{x['image_file_id']}" if x.get("image_file_id") else None}
              for x in s.get("slides", [])]
    return {"slides": slides, "courses": [public_course(c) for c in courses]}


@router.get("/public/images/{file_id}")
async def public_image(file_id: str):
    s = await db.settings.find_one({"id": "landing"}, {"_id": 0}) or {}
    used = any(x.get("image_file_id") == file_id for x in s.get("slides", [])) or \
        await db.courses.find_one({"image_file_id": file_id, "show_on_landing": True})
    rec = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0}) if used else None
    if not rec or not rec["content_type"].startswith("image/"):
        raise HTTPException(404, "Imagen no encontrada")
    data, _ = await asyncio.to_thread(get_object, rec["storage_path"])
    return Response(content=data, media_type=rec["content_type"], headers={"Cache-Control": "public, max-age=86400"})


class CheckoutIn(BaseModel):
    course_id: str
    email: EmailStr
    nombre: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    rut: str = ""
    accept_terms: bool = False


@router.post("/public/checkout")
async def checkout(body: CheckoutIn, request: Request):
    course = await db.courses.find_one({"id": body.course_id, "published": True, "show_on_landing": True}, {"_id": 0})
    if not course:
        raise HTTPException(404, "Curso no disponible")
    if not body.accept_terms:
        raise HTTPException(400, "Debes aceptar los Términos y Condiciones y la Política de Privacidad")
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0}) or \
        await create_user(body.email, body.nombre, body.apellidos, body.rut, "estudiante", "landing")
    if await db.enrollments.find_one({"user_id": user["id"], "course_id": course["id"]}):
        raise HTTPException(400, "Ya estás inscrito en este curso. Ingresa a la plataforma con tu correo.")
    await db.users.update_one({"id": user["id"]}, {"$set": {"terms_accepted_at": now_iso()}})
    base = app_base(request)
    if not course.get("price"):
        pay = await new_payment(user, course)
        await db.payments.update_one({"id": pay["id"]}, {"$set": {"base": base}})
        await grant_access({**pay, "base": base}, "landing")
        return {"free": True, "order_id": pay["id"]}
    await flow_conf()
    pay = await db.payments.find_one({"user_id": user["id"], "course_id": course["id"], "status": "pendiente"}, {"_id": 0}) \
        or await new_payment(user, course)
    try:
        link = await create_flow_link(pay, base)
    except HTTPException:
        if not pay.get("flow_token"):
            await db.payments.delete_one({"id": pay["id"]})
        raise
    return {"checkout_url": link, "order_id": pay["id"]}


@router.post("/payments/flow/confirm")
async def flow_confirm(token: str = Form(...)):
    try:
        await sync_payment(token)
    except HTTPException as ex:
        logger.error(f"Flow confirm: {ex.detail}")
    return {"ok": True}


@router.api_route("/payments/flow/return", methods=["GET", "POST"])
async def flow_return(request: Request):
    form = await request.form() if request.method == "POST" else request.query_params
    token = form.get("token", "")
    pay = await db.payments.find_one({"flow_token": token}, {"_id": 0, "id": 1})
    if pay:
        try:
            await sync_payment(token)
        except HTTPException:
            pass
    return RedirectResponse(f"{app_base(request)}/pago/resultado?orden={pay['id'] if pay else ''}", status_code=303)


@router.get("/public/payments/{order_id}")
async def public_payment(order_id: str):
    p = await db.payments.find_one({"id": order_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Orden no encontrada")
    return {k: p.get(k) for k in ("status", "course_title", "amount", "student_name", "email")}


# ---------- Admin: landing & payment settings ----------
class Slide(BaseModel):
    id: str = Field(default_factory=new_id)
    image_file_id: str = ""
    title: str = ""
    subtitle: str = ""


class LandingIn(BaseModel):
    slides: List[Slide] = []


@router.get("/admin/landing")
async def get_landing(_=Depends(admin_only)):
    s = await db.settings.find_one({"id": "landing"}, {"_id": 0}) or {}
    return {"slides": s.get("slides", [])}


@router.put("/admin/landing")
async def put_landing(body: LandingIn, _=Depends(admin_only)):
    await db.settings.update_one({"id": "landing"}, {"$set": {"slides": [x.model_dump() for x in body.slides]}}, upsert=True)
    return {"ok": True}


class PaySettingsIn(BaseModel):
    flow_env: str = "sandbox"
    flow_api_key: str = ""
    flow_secret_key: Optional[str] = None


@router.get("/admin/payment-settings")
async def get_pay_settings(_=Depends(admin_only)):
    s = await db.settings.find_one({"id": "payments"}, {"_id": 0}) or {}
    sec = s.get("flow_secret_key", "")
    return {"flow_env": s.get("flow_env", "sandbox"), "flow_api_key": s.get("flow_api_key", ""),
            "secret_set": bool(sec), "secret_hint": f"••••{sec[-4:]}" if sec else ""}


@router.put("/admin/payment-settings")
async def put_pay_settings(body: PaySettingsIn, _=Depends(admin_only)):
    if body.flow_env not in FLOW_URLS:
        raise HTTPException(400, "Ambiente inválido")
    upd = {"flow_env": body.flow_env, "flow_api_key": body.flow_api_key.strip()}
    if body.flow_secret_key:
        upd["flow_secret_key"] = body.flow_secret_key.strip()
    await db.settings.update_one({"id": "payments"}, {"$set": upd}, upsert=True)
    return await get_pay_settings()


# ---------- Admin: payments ----------
@router.get("/payments")
async def list_payments(_=Depends(staff_only)):
    return await db.payments.find({}, {"_id": 0, "flow_token": 0}).sort("created_at", -1).to_list(5000)


@router.post("/payments/{pay_id}/refresh")
async def refresh_payment(pay_id: str, _=Depends(admin_only)):
    p = await db.payments.find_one({"id": pay_id}, {"_id": 0})
    if not p or not p.get("flow_token"):
        raise HTTPException(400, "Este pago no tiene una orden en Flow")
    return await sync_payment(p["flow_token"])


@router.post("/payments/{pay_id}/mark-paid")
async def mark_paid(pay_id: str, request: Request, _=Depends(admin_only)):
    p = await db.payments.find_one({"id": pay_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Pago no encontrado")
    await db.payments.update_one({"id": pay_id}, {"$set": {"manual": True, "base": p.get("base") or app_base(request)}})
    await grant_access({**p, "base": p.get("base") or app_base(request)}, "pago_manual")
    return {"ok": True}


class SendLinkIn(BaseModel):
    user_id: Optional[str] = None
    payment_id: Optional[str] = None
    course_id: Optional[str] = None


@router.post("/payments/send-link")
async def send_link(body: SendLinkIn, request: Request, bg: BackgroundTasks, _=Depends(admin_only)):
    base = app_base(request)
    if body.payment_id:
        pay = await db.payments.find_one({"id": body.payment_id}, {"_id": 0})
        if not pay or pay["status"] == "pagado":
            raise HTTPException(400, "Este pago ya fue realizado o no existe")
    else:
        user = await db.users.find_one({"id": body.user_id}, {"_id": 0})
        course = await db.courses.find_one({"id": body.course_id}, {"_id": 0})
        if not user or not course or not course.get("price"):
            raise HTTPException(400, "Selecciona un estudiante y un curso con precio")
        await flow_conf()
        pay = await new_payment(user, course)
    try:
        link = await create_flow_link(pay, base)
    except HTTPException:
        if not body.payment_id:
            await db.payments.delete_one({"id": pay["id"]})
        raise
    await db.payments.update_one({"id": pay["id"]}, {"$set": {"link_sent_at": now_iso()}})
    html = email_html(f"Hola {pay['student_name']}",
                      f"<p>Te enviamos el enlace para pagar tu inscripción al curso <b>{escape(pay['course_title'])}</b> "
                      f"por <b>${pay['amount']:,}</b>.".replace(",", ".") + "</p><p>El pago se realiza de forma segura en Flow. "
                      "Al confirmarse, quedarás matriculado automáticamente.</p>", link, "Pagar mi curso")
    bg.add_task(send_email, to=pay["email"], subject=f"Link de pago: {pay['course_title']} – {EMAIL_FROM_NAME}", html=html)
    return {"ok": True, "checkout_url": link}
