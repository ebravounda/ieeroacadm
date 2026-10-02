import csv
import io
import hmac
import random
from zoneinfo import ZoneInfo
import secrets
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request, BackgroundTasks, UploadFile, File
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

import core
from core import (db, client, now, now_iso, new_id, create_token, get_current_user, require_roles,
                  send_email, otp_email_html, analyze_ai_usage, EMAIL_FROM_NAME, init_storage, put_object,
                  get_object, to_nota, APP_NAME, grade_email_html, create_file_token, read_file_token,
                  class_reminder_html, inactivity_email_html, weekly_report_html, cert_request_email_html,
                  cert_approved_email_html)
from certificate import render_certificate, template_to_png, DEFAULT_TEMPLATE
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("server")

app = FastAPI()
api = APIRouter(prefix="/api")

STAFF = ("admin", "docente")
admin_only = require_roles("admin")
staff_only = require_roles(*STAFF)


# ---------------- Models ----------------
class EmailIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    email: EmailStr
    code: str


class RegisterIn(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    rut: str = ""


class UserIn(BaseModel):
    email: EmailStr
    nombre: str
    apellidos: str
    rut: str = ""
    role: Literal["admin", "docente", "estudiante"] = "estudiante"
    course_id: Optional[str] = None


class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    rut: Optional[str] = None
    role: Optional[Literal["admin", "docente", "estudiante"]] = None
    active: Optional[bool] = None


class ImportIn(BaseModel):
    csv_text: str
    course_id: Optional[str] = None


class Question(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["single", "multiple", "open", "mc"] = "single"
    text: str
    options: List[str] = []
    correct: Optional[int] = None
    correct_multi: List[int] = []


class Quiz(BaseModel):
    questions: List[Question] = []
    pass_score: int = 75


class Material(BaseModel):
    id: str = Field(default_factory=new_id)
    type: Literal["texto", "video", "archivo", "enlace", "presentacion"]
    title: str
    body: str = ""
    url: str = ""
    file_id: str = ""
    file_name: str = ""
    content_type: str = ""
    section_id: str = ""


class Section(BaseModel):
    id: str = Field(default_factory=new_id)
    title: str = ""
    description: str = ""


class CourseIn(BaseModel):
    title: str
    description: str = ""
    code: str = ""
    hours: int = 0
    auto_enroll: bool = False
    published: bool = True
    price: int = Field(default=0, ge=0)
    summary: str = ""
    modality: str = ""
    image_file_id: str = ""
    show_on_landing: bool = False


class ModuleIn(BaseModel):
    title: str
    description: str = ""
    content: str = ""
    video_url: str = ""
    order: Optional[int] = None
    min_minutes: int = Field(default=0, ge=0)
    materials: List[Material] = []
    sections: List[Section] = []
    quiz: Quiz = Quiz()


class GradeIn(BaseModel):
    grades: dict
    feedback: str = ""


class EnrollIn(BaseModel):
    user_id: str
    course_id: str


class SubmitIn(BaseModel):
    answers: dict
    tab_switches: int = 0
    paste_events: int = 0
    duration_sec: int = 0


class LiveClassIn(BaseModel):
    course_id: str
    title: str
    platform: Literal["teams", "meet"]
    url: str
    start_at: str
    end_at: str


class SettingsIn(BaseModel):
    otec_name: Optional[str] = None
    rector_name: Optional[str] = None
    vicerrector_name: Optional[str] = None
    rector_signature: Optional[str] = None
    vicerrector_signature: Optional[str] = None
    directora_name: Optional[str] = None
    directora_signature: Optional[str] = None
    cert_template: Optional[dict] = None
    cert_layout: Optional[dict] = None


class RejectIn(BaseModel):
    reason: str = ""

# ---------------- Helpers ----------------
def public_user(u):
    return {k: u.get(k) for k in ("id", "email", "nombre", "apellidos", "rut", "role", "active", "created_at", "last_login")}


async def create_user(email, nombre, apellidos, rut="", role="estudiante", method="manual"):
    email = email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Ya existe un usuario con ese correo")
    doc = {"id": new_id(), "email": email, "nombre": nombre.strip(), "apellidos": apellidos.strip(), "rut": rut.strip(),
           "role": role, "active": True, "created_at": now_iso(), "last_login": None, "signup_method": method}
    await db.users.insert_one(doc)
    return public_user(doc)


async def enroll(user_id, course_id, method):
    if not await db.courses.find_one({"id": course_id}):
        raise HTTPException(404, "Curso no encontrado")
    existing = await db.enrollments.find_one({"user_id": user_id, "course_id": course_id}, {"_id": 0})
    if existing:
        return existing
    doc = {"id": new_id(), "user_id": user_id, "course_id": course_id, "method": method, "enrolled_at": now_iso(),
           "completed_modules": [], "final_passed": False, "completed_at": None}
    await db.enrollments.insert_one(doc)
    doc.pop("_id", None)
    asyncio.create_task(send_welcome(user_id, course_id))
    return doc


async def send_welcome(user_id, course_id):
    try:
        u = await db.users.find_one({"id": user_id}, {"_id": 0})
        c = await db.courses.find_one({"id": course_id}, {"_id": 0})
        n = await db.modules.count_documents({"course_id": course_id})
        base = core.PUBLIC_BASE if core.PUBLIC_BASE.startswith("https://") else ""
        html = core.welcome_email_html(u.get("nombre") or u["email"], u["email"], c["title"], n, c.get("hours"),
                                       f"{base}/login" if base else "")
        await send_email(to=u["email"], subject=f"Bienvenido(a) a {c['title']} – {EMAIL_FROM_NAME}", html=html)
    except Exception as e:
        logger.error(f"Welcome email failed: {e}")


async def auto_enroll(user_id):
    async for c in db.courses.find({"auto_enroll": True, "published": True}, {"_id": 0, "id": 1}):
        await enroll(user_id, c["id"], "automatica")


async def get_modules(course_id):
    return await db.modules.find({"course_id": course_id}, {"_id": 0}).sort("order", 1).to_list(500)


def strip_answers(quiz):
    qs = [{k: v for k, v in q.items() if k not in ("correct", "correct_multi")} for q in (quiz or {}).get("questions", [])]
    for q in qs:
        if q["type"] == "mc":
            q["type"] = "single"
    return {"questions": qs, "pass_score": (quiz or {}).get("pass_score", 75)}


def auto_grade(quiz, answers):
    res = {}
    for q in quiz.get("questions", []):
        a = answers.get(q["id"])
        kind = "single" if q["type"] == "mc" else q["type"]
        if kind == "single":
            res[q["id"]] = 100 if a is not None and str(a) == str(q.get("correct")) else 0
        elif kind == "multiple":
            chosen = sorted(int(x) for x in (a or []) if str(x).lstrip("-").isdigit())
            res[q["id"]] = 100 if chosen and chosen == sorted(q.get("correct_multi") or []) else 0
        else:
            res[q["id"]] = None if str(a or "").strip() else 0
    return res


def score_of(results):
    if not results or any(v is None for v in results.values()):
        return None
    return round(sum(results.values()) / len(results))


async def module_minutes(user_id, module_id):
    s = await db.module_sessions.find_one({"user_id": user_id, "module_id": module_id}, {"_id": 0, "duration_sec": 1})
    return round((s["duration_sec"] if s else 0) / 60, 1)


async def require_min_time(user, m):
    need = m.get("min_minutes", 0)
    spent = await module_minutes(user["id"], m["id"])
    if spent < need:
        raise HTTPException(400, f"Debes dedicar al menos {need} min al módulo (llevas {spent:g} min)")


def module_tasks_done(m, e):
    done = set((e.get("completed_tasks") or {}).get(m["id"], []))
    return all(x["id"] in done for x in m.get("materials", []))


def course_grades(e, course, modules):
    exig = course.get("final_exam", {}).get("pass_score", 75)
    results = e.get("module_results") or {}
    mods = []
    for m in modules:
        if m.get("quiz", {}).get("questions"):
            pct = results.get(m["id"])
            mods.append({"module_id": m["id"], "title": m["title"], "pct": pct,
                         "nota": to_nota(pct, m["quiz"].get("pass_score", 75))})
    pcts = [x["pct"] for x in mods if x["pct"] is not None]
    mod_avg = round(sum(pcts) / len(pcts)) if pcts else None
    final = e.get("final_score")
    overall = round((mod_avg + final) / 2) if mod_avg is not None and final is not None else None
    return {"modules": mods, "modules_avg_pct": mod_avg, "modules_avg_nota": to_nota(mod_avg, exig),
            "final_pct": final, "final_nota": to_nota(final, exig),
            "overall_pct": overall, "overall_nota": to_nota(overall, exig)}


def module_status(modules, completed):
    out, prev_done = [], True
    for m in modules:
        done = m["id"] in completed
        out.append({"id": m["id"], "unlocked": prev_done, "completed": done})
        prev_done = done
    return out


async def require_enrollment(user, course_id):
    e = await db.enrollments.find_one({"user_id": user["id"], "course_id": course_id}, {"_id": 0})
    if not e:
        raise HTTPException(403, "No estás matriculado en este curso")
    return e


async def run_ai_analysis(sub_id):
    sub = await db.submissions.find_one({"id": sub_id}, {"_id": 0})
    try:
        result = await analyze_ai_usage(sub["questions"], sub["answers"], sub["behavior"])
        await db.submissions.update_one({"id": sub_id}, {"$set": {"ai_analysis": result, "ai_status": "completado"}})
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        await db.submissions.update_one({"id": sub_id}, {"$set": {"ai_status": "error"}})


CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def approval_code():
    pick = lambda: "".join(secrets.choice(CODE_CHARS) for _ in range(4))  # noqa: E731
    return f"IBA-{pick()}-{pick()}"


async def notify_admins_certificate(d):
    async for a in db.users.find({"role": "admin", "active": True}, {"_id": 0, "email": 1, "nombre": 1}):
        try:
            await send_email(to=a["email"], subject=f"Solicitud de aprobación de certificado – {d['student_name']}",
                             html=cert_request_email_html(a["nombre"], d["student_name"], d["course_title"],
                                                          d.get("nota_final")))
        except Exception as ex:
            logger.error(f"Certificate request email failed: {ex}")


async def issue_diploma(user, course, nota=None):
    existing = await db.diplomas.find_one({"user_id": user["id"], "course_id": course["id"]}, {"_id": 0})
    if existing:
        return existing
    doc = {"id": new_id(), "code": approval_code(), "user_id": user["id"], "course_id": course["id"],
           "student_name": f"{user['nombre']} {user['apellidos']}", "rut": user.get("rut", ""),
           "course_title": course["title"], "hours": course.get("hours", 0), "nota_final": nota,
           "status": "pendiente", "issued_at": now_iso()}
    await db.diplomas.insert_one(doc)
    doc.pop("_id", None)
    asyncio.create_task(notify_admins_certificate(doc))
    return doc


async def get_settings():
    s = await db.settings.find_one({"id": "global"}, {"_id": 0}) or {}
    return {"id": "global", "otec_name": EMAIL_FROM_NAME, "rector_name": "", "vicerrector_name": "",
            "rector_signature": "", "vicerrector_signature": "", "directora_name": "", "directora_signature": "",
            "cert_template": {}, "cert_layout": {}, **s}


# ---------------- Auth ----------------
async def send_code(user):
    last = await db.otp_codes.find_one({"email": user["email"]})
    if last and (now() - datetime.fromisoformat(last["created_at"])).total_seconds() < 30:
        raise HTTPException(429, "Espera unos segundos antes de solicitar otro código")
    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    await db.otp_codes.update_one({"email": user["email"]}, {"$set": {
        "email": user["email"], "code": code, "attempts": 0, "created_at": now_iso(),
        "expires_at": now() + timedelta(minutes=10)}}, upsert=True)
    await send_email(to=user["email"], subject=f"Tu código de acceso a {EMAIL_FROM_NAME}",
                     html=otp_email_html(user["nombre"], code))


@api.post("/auth/request-code")
async def request_code(body: EmailIn):
    user = await db.users.find_one({"email": body.email.lower(), "active": True}, {"_id": 0})
    if not user:
        raise HTTPException(404, "No existe una cuenta activa con ese correo")
    await send_code(user)
    return {"ok": True}


@api.post("/auth/register")
async def register(body: RegisterIn):
    user = await create_user(body.email, body.nombre, body.apellidos, body.rut, "estudiante", "autoregistro")
    await auto_enroll(user["id"])
    await send_code(user)
    return {"ok": True}


async def remember_public_base(base):
    if base.startswith("https://") and core.PUBLIC_BASE != base:
        core.PUBLIC_BASE = base
        await db.app_meta.update_one({"id": "public"}, {"$set": {"base": base}}, upsert=True)


@api.post("/auth/verify-code")
async def verify_code(body: VerifyIn, request: Request, response: Response):
    email = body.email.lower()
    rec = await db.otp_codes.find_one({"email": email})
    if not rec:
        raise HTTPException(400, "Solicita un nuevo código")
    expires = rec["expires_at"].replace(tzinfo=now().tzinfo) if rec["expires_at"].tzinfo is None else rec["expires_at"]
    if expires < now():
        raise HTTPException(400, "El código expiró, solicita uno nuevo")
    if rec["attempts"] >= 5:
        raise HTTPException(429, "Demasiados intentos, solicita un nuevo código")
    if rec["code"] != body.code.strip():
        await db.otp_codes.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "Código incorrecto")
    await db.otp_codes.delete_one({"email": email})
    user = await db.users.find_one({"email": email, "active": True}, {"_id": 0})
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login": now_iso()}})
    await db.access_logs.insert_one({"user_id": user["id"], "ts": now_iso(),
                                     "ip": request.client.host if request.client else ""})
    token = create_token(user["id"])
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    await remember_public_base(app_base(request))
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return public_user(user)


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


# ---------------- Activity (attendance / permanence) ----------------
class HeartbeatIn(BaseModel):
    course_id: Optional[str] = None
    module_id: Optional[str] = None


async def track_time(coll, key: dict, t):
    sess = await coll.find_one(key)
    if sess:
        gap = (t - datetime.fromisoformat(sess["last_seen"])).total_seconds()
        await coll.update_one({"_id": sess["_id"]}, {"$set": {"last_seen": t.isoformat()},
                                                     "$inc": {"duration_sec": int(min(max(gap, 0), 90))}})
    else:
        await coll.insert_one({"id": new_id(), **key, "started_at": t.isoformat(), "last_seen": t.isoformat(),
                               "duration_sec": 0})


@api.post("/activity/heartbeat")
async def heartbeat(body: Optional[HeartbeatIn] = None, user=Depends(get_current_user)):
    t = now()
    date = t.date().isoformat()
    await track_time(db.sessions, {"user_id": user["id"], "date": date}, t)
    course_id = body.course_id if body else None
    if body and body.module_id and not course_id:
        m = await db.modules.find_one({"id": body.module_id}, {"_id": 0, "course_id": 1})
        course_id = m["course_id"] if m else None
    if course_id and await db.enrollments.find_one({"user_id": user["id"], "course_id": course_id}):
        await track_time(db.course_sessions, {"user_id": user["id"], "course_id": course_id, "date": date}, t)
        if body.module_id:
            await track_time(db.module_sessions, {"user_id": user["id"], "module_id": body.module_id}, t)
    return {"ok": True}


# ---------------- Users ----------------
@api.get("/users")
async def list_users(role: Optional[str] = None, _=Depends(staff_only)):
    q = {"role": role} if role else {}
    return [public_user(u) for u in await db.users.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)]


@api.post("/users")
async def add_user(body: UserIn, _=Depends(admin_only)):
    user = await create_user(body.email, body.nombre, body.apellidos, body.rut, body.role, "manual")
    if body.course_id and body.role == "estudiante":
        await enroll(user["id"], body.course_id, "manual")
    return user


@api.put("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate, _=Depends(admin_only)):
    upd = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None}
    if "nombre" in upd and not upd["nombre"]:
        raise HTTPException(400, "El nombre es obligatorio")
    await db.users.update_one({"id": user_id}, {"$set": upd})
    u = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    return public_user(u)


@api.post("/users/import")
async def import_users(body: ImportIn, _=Depends(admin_only)):
    reader = csv.DictReader(io.StringIO(body.csv_text.strip()))
    created, errors = 0, []
    for i, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            if not row.get("email") or not row.get("nombre"):
                raise HTTPException(400, "Faltan email o nombre")
            EmailIn(email=row["email"])
            u = await create_user(row["email"], row["nombre"], row.get("apellidos", ""), row.get("rut", ""),
                                  "estudiante", "importacion")
            if body.course_id:
                await enroll(u["id"], body.course_id, "automatica")
            created += 1
        except HTTPException as e:
            errors.append(f"Fila {i}: {e.detail}")
        except Exception:
            errors.append(f"Fila {i}: correo inválido")
    return {"created": created, "errors": errors}


# ---------------- Courses & modules ----------------
@api.get("/courses")
async def list_courses(user=Depends(get_current_user)):
    q = {} if user["role"] in STAFF else {"published": True}
    courses = await db.courses.find(q, {"_id": 0, "final_exam": 0}).sort("created_at", -1).to_list(500)
    for c in courses:
        c["module_count"] = await db.modules.count_documents({"course_id": c["id"]})
        c["student_count"] = await db.enrollments.count_documents({"course_id": c["id"]})
    return courses


@api.post("/courses")
async def create_course(body: CourseIn, user=Depends(staff_only)):
    doc = {"id": new_id(), **body.model_dump(), "teacher_id": user["id"], "created_at": now_iso(),
           "final_exam": Quiz().model_dump()}
    await db.courses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/courses/{course_id}")
async def update_course(course_id: str, body: CourseIn, _=Depends(staff_only)):
    await db.courses.update_one({"id": course_id}, {"$set": body.model_dump()})
    return await db.courses.find_one({"id": course_id}, {"_id": 0})


@api.delete("/courses/{course_id}")
async def delete_course(course_id: str, _=Depends(admin_only)):
    await db.courses.delete_one({"id": course_id})
    await db.modules.delete_many({"course_id": course_id})
    await db.enrollments.delete_many({"course_id": course_id})
    return {"ok": True}


@api.put("/courses/{course_id}/final-exam")
async def set_final_exam(course_id: str, body: Quiz, _=Depends(staff_only)):
    await db.courses.update_one({"id": course_id}, {"$set": {"final_exam": body.model_dump()}})
    return {"ok": True}


@api.get("/courses/{course_id}")
async def get_course(course_id: str, user=Depends(get_current_user)):
    course = await db.courses.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(404, "Curso no encontrado")
    modules = await get_modules(course_id)
    if user["role"] in STAFF:
        course["modules"] = modules
        return course
    e = await db.enrollments.find_one({"user_id": user["id"], "course_id": course_id}, {"_id": 0})
    course["final_exam"] = {"question_count": len(course["final_exam"]["questions"]),
                            "pass_score": course["final_exam"]["pass_score"]}
    course["modules"] = [{k: m[k] for k in ("id", "title", "description", "order")} for m in modules]
    course["enrollment"] = e
    if e:
        st = {s["id"]: s for s in module_status(modules, e["completed_modules"])}
        for m in course["modules"]:
            m.update(st[m["id"]])
        course["final_unlocked"] = all(s["completed"] for s in st.values()) and len(modules) > 0
        course["grades"] = course_grades(e, {**course, "final_exam": {"pass_score": course["final_exam"]["pass_score"]}}, modules)
        diploma = await db.diplomas.find_one({"user_id": user["id"], "course_id": course_id}, {"_id": 0, "code": 1})
        course["diploma_code"] = diploma["code"] if diploma else None
    return course


@api.post("/courses/{course_id}/modules")
async def add_module(course_id: str, body: ModuleIn, _=Depends(staff_only)):
    count = await db.modules.count_documents({"course_id": course_id})
    doc = {"id": new_id(), "course_id": course_id, **body.model_dump()}
    doc["order"] = body.order if body.order is not None else count + 1
    await db.modules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/modules/{module_id}")
async def update_module(module_id: str, body: ModuleIn, _=Depends(staff_only)):
    upd = body.model_dump()
    if body.order is None:
        upd.pop("order")
    await db.modules.update_one({"id": module_id}, {"$set": upd})
    return await db.modules.find_one({"id": module_id}, {"_id": 0})


@api.delete("/modules/{module_id}")
async def delete_module(module_id: str, _=Depends(staff_only)):
    await db.modules.delete_one({"id": module_id})
    return {"ok": True}


async def accessible_module(module_id, user):
    m = await db.modules.find_one({"id": module_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Módulo no encontrado")
    if user["role"] in STAFF:
        return m, None
    e = await require_enrollment(user, m["course_id"])
    modules = await get_modules(m["course_id"])
    st = next(s for s in module_status(modules, e["completed_modules"]) if s["id"] == module_id)
    if not st["unlocked"]:
        raise HTTPException(403, "Debes completar el módulo anterior para acceder")
    m["completed"] = st["completed"]
    return m, e


SUB_PUBLIC = {"_id": 0, "score": 1, "passed": 1, "status": 1, "nota": 1, "pass_score": 1, "feedback": 1, "created_at": 1}


async def last_submission(user_id, course_id, module_id):
    rows = await db.submissions.find({"user_id": user_id, "course_id": course_id, "module_id": module_id},
                                     SUB_PUBLIC).sort("created_at", -1).to_list(1)
    return rows[0] if rows else None


@api.get("/modules/{module_id}")
async def get_module(module_id: str, user=Depends(get_current_user)):
    m, e = await accessible_module(module_id, user)
    if user["role"] not in STAFF:
        m["quiz"] = strip_answers(m.get("quiz"))
        m["completed_tasks"] = (e.get("completed_tasks") or {}).get(module_id, [])
        m["tasks_done"] = module_tasks_done(m, e)
        m["time_spent_min"] = await module_minutes(user["id"], module_id)
        m["min_minutes"] = m.get("min_minutes", 0)
        m["time_ok"] = m["time_spent_min"] >= m["min_minutes"]
        m["last_submission"] = await last_submission(user["id"], m["course_id"], module_id)
    return m


@api.post("/modules/{module_id}/tasks/{material_id}/complete")
async def complete_task(module_id: str, material_id: str, user=Depends(get_current_user)):
    m, e = await accessible_module(module_id, user)
    if not e:
        raise HTTPException(400, "Solo estudiantes")
    if not any(x["id"] == material_id for x in m.get("materials", [])):
        raise HTTPException(404, "Tarea no encontrada")
    await db.enrollments.update_one({"id": e["id"]}, {"$addToSet": {f"completed_tasks.{module_id}": material_id}})
    return {"ok": True}


@api.post("/modules/{module_id}/complete")
async def complete_module(module_id: str, user=Depends(get_current_user)):
    m, e = await accessible_module(module_id, user)
    if not e:
        raise HTTPException(400, "Solo estudiantes")
    if m.get("quiz", {}).get("questions"):
        raise HTTPException(400, "Este módulo requiere aprobar la evaluación")
    if not module_tasks_done(m, e):
        raise HTTPException(400, "Debes completar todas las tareas del módulo")
    await require_min_time(user, m)
    await db.enrollments.update_one({"id": e["id"]}, {"$addToSet": {"completed_modules": module_id}})
    return {"ok": True}


async def apply_result(sub):
    """Apply a fully graded submission to the enrollment (module progress / final / diploma)."""
    e = await db.enrollments.find_one({"user_id": sub["user_id"], "course_id": sub["course_id"]}, {"_id": 0})
    if not e:
        return None
    mid = sub["module_id"]
    if mid:
        if sub["passed"]:
            await db.enrollments.update_one({"id": e["id"]}, {"$addToSet": {"completed_modules": mid},
                                                            "$set": {f"module_results.{mid}": sub["score"]}})
        else:
            await db.enrollments.update_one({"id": e["id"]}, {"$set": {f"completed_tasks.{mid}": []}})
            await db.module_sessions.delete_one({"user_id": sub["user_id"], "module_id": mid})
        return None
    if not sub["passed"]:
        return None
    await db.enrollments.update_one({"id": e["id"]}, {"$set": {"final_passed": True, "final_score": sub["score"],
                                                            "completed_at": now_iso()}})
    e["final_score"] = sub["score"]
    course = await db.courses.find_one({"id": sub["course_id"]}, {"_id": 0})
    user = await db.users.find_one({"id": sub["user_id"]}, {"_id": 0})
    grades = course_grades(e, course, await get_modules(course["id"]))
    return await issue_diploma(user, course, grades["overall_nota"])


def finalize_fields(sub, results):
    score = score_of(results)
    sub["question_scores"] = results
    if score is None:
        sub.update({"status": "en_revision", "score": None, "passed": None, "nota": None})
    else:
        sub.update({"status": "calificada", "score": score, "passed": score >= sub["pass_score"],
                    "nota": to_nota(score, sub["pass_score"])})


async def save_submission(user, course_id, module_id, quiz, body: SubmitIn, bg: BackgroundTasks):
    pending = await db.submissions.find_one({"user_id": user["id"], "course_id": course_id, "module_id": module_id,
                                             "status": "en_revision"})
    if pending:
        raise HTTPException(400, "Tu evaluación anterior está en revisión por el docente")
    sub = {"id": new_id(), "user_id": user["id"], "student_name": f"{user['nombre']} {user['apellidos']}",
           "course_id": course_id, "module_id": module_id, "kind": "final" if module_id is None else "modulo",
           "questions": quiz["questions"], "answers": body.answers, "pass_score": quiz.get("pass_score", 75),
           "feedback": "",
           "behavior": {"tab_switches": body.tab_switches, "paste_events": body.paste_events,
                        "duration_sec": body.duration_sec},
           "ai_status": "pendiente", "ai_analysis": None, "created_at": now_iso()}
    finalize_fields(sub, auto_grade(quiz, body.answers))
    await db.submissions.insert_one(sub)
    sub.pop("_id", None)
    bg.add_task(run_ai_analysis, sub["id"])
    diploma = await apply_result(sub) if sub["status"] == "calificada" else None
    return {k: sub[k] for k in ("score", "passed", "status", "nota", "pass_score")} | {
        "diploma_code": diploma["code"] if diploma else None}


@api.post("/modules/{module_id}/submit")
async def submit_module(module_id: str, body: SubmitIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    m, e = await accessible_module(module_id, user)
    if not e:
        raise HTTPException(400, "Solo estudiantes")
    if not m.get("quiz", {}).get("questions"):
        raise HTTPException(400, "Este módulo no tiene evaluación")
    if module_id in e["completed_modules"]:
        raise HTTPException(400, "Ya aprobaste este módulo")
    if not module_tasks_done(m, e):
        raise HTTPException(400, "Debes completar todas las tareas del módulo antes del examen")
    await require_min_time(user, m)
    return await save_submission(user, m["course_id"], module_id, m["quiz"], body, bg)


@api.get("/courses/{course_id}/final-exam")
async def get_final_exam(course_id: str, user=Depends(get_current_user)):
    course = await db.courses.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(404, "Curso no encontrado")
    if user["role"] in STAFF:
        return course["final_exam"]
    e = await require_enrollment(user, course_id)
    modules = await get_modules(course_id)
    if not modules or not all(m["id"] in e["completed_modules"] for m in modules):
        raise HTTPException(403, "Debes aprobar todos los exámenes de módulo")
    return {**strip_answers(course["final_exam"]), "course_title": course["title"], "final_passed": e["final_passed"],
            "last_submission": await last_submission(user["id"], course_id, None)}


@api.post("/courses/{course_id}/final-exam/submit")
async def submit_final(course_id: str, body: SubmitIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    course = await db.courses.find_one({"id": course_id}, {"_id": 0})
    e = await require_enrollment(user, course_id)
    modules = await get_modules(course_id)
    if not modules or not all(m["id"] in e["completed_modules"] for m in modules):
        raise HTTPException(403, "Debes aprobar todos los exámenes de módulo")
    if e["final_passed"]:
        raise HTTPException(400, "Ya aprobaste la evaluación final")
    if not course["final_exam"]["questions"]:
        raise HTTPException(400, "El curso aún no tiene evaluación final")
    return await save_submission(user, course_id, None, course["final_exam"], body, bg)


# ---------------- Enrollments ----------------
@api.post("/enrollments")
async def manual_enroll(body: EnrollIn, _=Depends(staff_only)):
    if not await db.users.find_one({"id": body.user_id}):
        raise HTTPException(404, "Usuario no encontrado")
    return await enroll(body.user_id, body.course_id, "manual")


@api.post("/courses/{course_id}/enroll")
async def self_enroll(course_id: str, user=Depends(get_current_user)):
    course = await db.courses.find_one({"id": course_id, "published": True})
    if not course or not course.get("auto_enroll"):
        raise HTTPException(403, "Este curso requiere matrícula manual por la institución")
    return await enroll(user["id"], course_id, "automatica")


@api.get("/courses/{course_id}/enrollments")
async def course_enrollments(course_id: str, _=Depends(staff_only)):
    total = await db.modules.count_documents({"course_id": course_id})
    rows = await db.enrollments.find({"course_id": course_id}, {"_id": 0}).to_list(5000)
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": [r["user_id"] for r in rows]}}, {"_id": 0}).to_list(5000)}
    for r in rows:
        u = users.get(r["user_id"], {})
        r["student_name"] = f"{u.get('nombre', '')} {u.get('apellidos', '')}"
        r["email"] = u.get("email")
        r["progress"] = round(len(r["completed_modules"]) / total * 100) if total else 0
    return rows


@api.delete("/enrollments/{enrollment_id}")
async def delete_enrollment(enrollment_id: str, _=Depends(admin_only)):
    await db.enrollments.delete_one({"id": enrollment_id})
    return {"ok": True}


@api.get("/my/courses")
async def my_courses(user=Depends(get_current_user)):
    rows = await db.enrollments.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    out = []
    for r in rows:
        c = await db.courses.find_one({"id": r["course_id"]}, {"_id": 0, "final_exam": 0})
        if not c:
            continue
        total = await db.modules.count_documents({"course_id": c["id"]})
        c["progress"] = round(len(r["completed_modules"]) / total * 100) if total else 0
        c["module_count"] = total
        c["completed_count"] = len(r["completed_modules"])
        c["final_passed"] = r["final_passed"]
        full = await db.courses.find_one({"id": c["id"]}, {"_id": 0, "final_exam.pass_score": 1})
        c["grades"] = course_grades(r, full, await get_modules(c["id"]))
        out.append(c)
    return out


# ---------------- Submissions / AI ----------------
@api.get("/submissions")
async def list_submissions(course_id: Optional[str] = None, _=Depends(staff_only)):
    q = {"course_id": course_id} if course_id else {}
    subs = await db.submissions.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    titles = {c["id"]: c["title"] for c in await db.courses.find({}, {"_id": 0, "id": 1, "title": 1}).to_list(500)}
    mods = {m["id"]: m["title"] for m in await db.modules.find({}, {"_id": 0, "id": 1, "title": 1}).to_list(5000)}
    for s in subs:
        s["course_title"] = titles.get(s["course_id"], "")
        s["module_title"] = mods.get(s["module_id"], "Evaluación final") if s["module_id"] else "Evaluación final"
    return subs


@api.post("/submissions/{sub_id}/grade")
async def grade_submission(sub_id: str, body: GradeIn, bg: BackgroundTasks, _=Depends(staff_only)):
    sub = await db.submissions.find_one({"id": sub_id}, {"_id": 0})
    if not sub:
        raise HTTPException(404, "Entrega no encontrada")
    if sub.get("status") != "en_revision":
        raise HTTPException(400, "Esta entrega ya fue calificada")
    results = dict(sub.get("question_scores") or {})
    for q in sub["questions"]:
        if results.get(q["id"]) is None:
            val = body.grades.get(q["id"])
            if val is None:
                raise HTTPException(400, "Debes calificar todas las preguntas de desarrollo")
            results[q["id"]] = max(0, min(100, int(val)))
    sub["feedback"] = body.feedback
    finalize_fields(sub, results)
    await db.submissions.update_one({"id": sub_id}, {"$set": {k: sub[k] for k in (
        "question_scores", "status", "score", "passed", "nota", "feedback")}})
    await apply_result(sub)
    bg.add_task(notify_grade, sub)
    return sub


async def notify_grade(sub):
    try:
        user = await db.users.find_one({"id": sub["user_id"]}, {"_id": 0})
        course = await db.courses.find_one({"id": sub["course_id"]}, {"_id": 0, "title": 1})
        mod = await db.modules.find_one({"id": sub["module_id"]}, {"_id": 0, "title": 1}) if sub["module_id"] else None
        exam = f"examen del módulo “{mod['title']}”" if mod else "evaluación final"
        await send_email(to=user["email"], subject=f"Tu nota en {course['title']} – {EMAIL_FROM_NAME}",
                         html=grade_email_html(user["nombre"], course["title"], exam, sub["nota"], sub["score"],
                                               sub["passed"], sub.get("feedback", "")))
    except Exception as e:
        logger.error(f"Grade email failed: {e}")


@api.post("/submissions/{sub_id}/analyze")
async def reanalyze(sub_id: str, _=Depends(staff_only)):
    if not await db.submissions.find_one({"id": sub_id}):
        raise HTTPException(404, "Entrega no encontrada")
    await db.submissions.update_one({"id": sub_id}, {"$set": {"ai_status": "pendiente"}})
    await run_ai_analysis(sub_id)
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


# ---------------- Live classes ----------------
def class_status(c):
    t = now()
    start, end = datetime.fromisoformat(c["start_at"]), datetime.fromisoformat(c["end_at"])
    if start.tzinfo is None:
        start, end = start.replace(tzinfo=t.tzinfo), end.replace(tzinfo=t.tzinfo)
    if t < start - timedelta(minutes=10):
        return "programada"
    if t <= end:
        return "en_vivo"
    return "finalizada"


@api.get("/live-classes")
async def list_live(user=Depends(get_current_user)):
    q = {}
    if user["role"] not in STAFF:
        ids = [e["course_id"] for e in await db.enrollments.find({"user_id": user["id"]}, {"course_id": 1}).to_list(500)]
        q = {"course_id": {"$in": ids}}
    rows = await db.live_classes.find(q, {"_id": 0}).sort("start_at", 1).to_list(1000)
    titles = {c["id"]: c["title"] for c in await db.courses.find({}, {"_id": 0, "id": 1, "title": 1}).to_list(500)}
    for r in rows:
        r["status"] = class_status(r)
        r["course_title"] = titles.get(r["course_id"], "")
        r["attendees"] = await db.live_attendance.count_documents({"class_id": r["id"]})
        if user["role"] not in STAFF:
            r["attended"] = bool(await db.live_attendance.find_one({"class_id": r["id"], "user_id": user["id"]}))
        if user["role"] not in STAFF and r["status"] != "en_vivo":
            r.pop("url")
    return rows


@api.post("/live-classes")
async def create_live(body: LiveClassIn, _=Depends(staff_only)):
    if not body.url.startswith("https://"):
        raise HTTPException(400, "El enlace debe comenzar con https://")
    doc = {"id": new_id(), **body.model_dump(), "created_at": now_iso()}
    await db.live_classes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.delete("/live-classes/{class_id}")
async def delete_live(class_id: str, _=Depends(staff_only)):
    await db.live_classes.delete_one({"id": class_id})
    return {"ok": True}


@api.post("/live-classes/{class_id}/join")
async def join_live(class_id: str, user=Depends(get_current_user)):
    c = await db.live_classes.find_one({"id": class_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Clase no encontrada")
    if user["role"] not in STAFF:
        await require_enrollment(user, c["course_id"])
        if class_status(c) != "en_vivo":
            raise HTTPException(400, "La clase no está en vivo")
        await db.live_attendance.update_one({"class_id": class_id, "user_id": user["id"]},
                                            {"$setOnInsert": {"joined_at": now_iso()}}, upsert=True)
    return {"url": c["url"]}


@api.get("/live-classes/{class_id}/attendance")
async def live_attendance(class_id: str, _=Depends(staff_only)):
    c = await db.live_classes.find_one({"id": class_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Clase no encontrada")
    joined = {r["user_id"]: r["joined_at"] for r in await db.live_attendance.find({"class_id": class_id}, {"_id": 0}).to_list(5000)}
    enrolled = [e["user_id"] for e in await db.enrollments.find({"course_id": c["course_id"]}, {"user_id": 1}).to_list(5000)]
    ids = list(dict.fromkeys(enrolled + list(joined)))
    users = await db.users.find({"id": {"$in": ids}, "role": "estudiante"}, {"_id": 0}).to_list(5000)
    rows = [{"student_name": f"{u['nombre']} {u['apellidos']}", "rut": u.get("rut", ""), "email": u["email"],
             "present": u["id"] in joined, "joined_at": joined.get(u["id"])} for u in users]
    rows.sort(key=lambda r: (not r["present"], r["student_name"].lower()))
    course = await db.courses.find_one({"id": c["course_id"]}, {"_id": 0, "title": 1}) or {"title": ""}
    return {"class": {**c, "course_title": course["title"], "status": class_status(c)}, "rows": rows,
            "present": sum(r["present"] for r in rows), "total": len(rows)}


# ---------------- Analytics ----------------
@api.get("/analytics/overview")
async def analytics_overview(_=Depends(staff_only)):
    today = now().date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    daily = []
    for d in days:
        sess = await db.sessions.find({"date": d}, {"_id": 0, "duration_sec": 1}).to_list(10000)
        daily.append({"date": d[5:], "activos": len(sess), "minutos": round(sum(s["duration_sec"] for s in sess) / 60)})
    subs = await db.submissions.find({"ai_status": "completado"}, {"_id": 0, "ai_analysis.percentage": 1}).to_list(10000)
    ai_vals = [s["ai_analysis"]["percentage"] for s in subs]
    return {
        "students": await db.users.count_documents({"role": "estudiante"}),
        "courses": await db.courses.count_documents({}),
        "enrollments": await db.enrollments.count_documents({}),
        "diplomas": await db.diplomas.count_documents({}),
        "active_today": daily[-1]["activos"],
        "ai_avg": round(sum(ai_vals) / len(ai_vals)) if ai_vals else 0,
        "ai_high": sum(1 for v in ai_vals if v >= 60),
        "daily": daily,
    }


@api.get("/analytics/students")
async def analytics_students(_=Depends(staff_only)):
    students = await db.users.find({"role": "estudiante"}, {"_id": 0}).to_list(5000)
    mod_counts = {}
    async for m in db.modules.find({}, {"course_id": 1}):
        mod_counts[m["course_id"]] = mod_counts.get(m["course_id"], 0) + 1
    out = []
    for s in students:
        sess = await db.sessions.find({"user_id": s["id"]}, {"_id": 0, "duration_sec": 1}).to_list(5000)
        ens = await db.enrollments.find({"user_id": s["id"]}, {"_id": 0}).to_list(500)
        subs = await db.submissions.find({"user_id": s["id"], "score": {"$ne": None}},
                                         {"_id": 0, "score": 1, "nota": 1, "ai_analysis": 1}).to_list(1000)
        notas = [x["nota"] for x in subs if x.get("nota") is not None]
        progs = [round(len(e["completed_modules"]) / mod_counts[e["course_id"]] * 100) for e in ens if mod_counts.get(e["course_id"])]
        ai = [x["ai_analysis"]["percentage"] for x in subs if x.get("ai_analysis")]
        out.append({**public_user(s),
                    "days_attended": len(sess),
                    "total_minutes": round(sum(x["duration_sec"] for x in sess) / 60),
                    "logins": await db.access_logs.count_documents({"user_id": s["id"]}),
                    "courses": len(ens),
                    "progress": round(sum(progs) / len(progs)) if progs else 0,
                    "avg_score": round(sum(x["score"] for x in subs) / len(subs)) if subs else None,
                    "avg_nota": round(sum(notas) / len(notas), 1) if notas else None,
                    "ai_avg": round(sum(ai) / len(ai)) if ai else None})
    return out


@api.get("/my/progress")
async def my_progress(user=Depends(get_current_user)):
    out = []
    for e in await db.enrollments.find({"user_id": user["id"]}, {"_id": 0}).to_list(500):
        course = await db.courses.find_one({"id": e["course_id"]}, {"_id": 0})
        if not course:
            continue
        modules = await get_modules(course["id"])
        status = {s["id"]: s for s in module_status(modules, e["completed_modules"])}
        done_tasks = e.get("completed_tasks") or {}
        rows, next_step = [], None
        for m in modules:
            st = status[m["id"]]
            mats = m.get("materials", [])
            spent = await module_minutes(user["id"], m["id"])
            missing = max(0, m.get("min_minutes", 0) - spent)
            pending = [x["title"] for x in mats if x["id"] not in done_tasks.get(m["id"], [])]
            has_quiz = bool(m.get("quiz", {}).get("questions"))
            last = await last_submission(user["id"], course["id"], m["id"]) if has_quiz else None
            state = "completado" if st["completed"] else "en_curso" if st["unlocked"] else "bloqueado"
            rows.append({"id": m["id"], "title": m["title"], "order": m["order"], "state": state,
                         "tasks_total": len(mats), "tasks_done": len(mats) - len(pending),
                         "pending_tasks": pending if state == "en_curso" else [], "has_quiz": has_quiz,
                         "exam_status": last["status"] if last else None,
                         "time_spent_min": spent, "min_minutes": m.get("min_minutes", 0),
                         "nota": to_nota(e.get("module_results", {}).get(m["id"]), m.get("quiz", {}).get("pass_score", 75))})
            if state == "en_curso" and not next_step:
                if last and last["status"] == "en_revision":
                    text = f"Espera la corrección del examen de “{m['title']}”"
                elif pending:
                    text = f"Completa la tarea “{pending[0]}” de “{m['title']}”"
                elif missing > 0:
                    text = f"Dedica {int(-(-missing // 1))} min más al módulo “{m['title']}” para habilitar el examen"
                elif has_quiz:
                    text = f"Rinde el examen de “{m['title']}”"
                else:
                    text = f"Finaliza el módulo “{m['title']}”"
                next_step = {"text": text, "link": f"/modulo/{m['id']}"}
        diploma = await db.diplomas.find_one({"user_id": user["id"], "course_id": course["id"]}, {"_id": 0, "code": 1})
        if not next_step:
            if diploma:
                next_step = {"text": "¡Curso aprobado! Descarga tu diploma", "link": f"/diploma/{diploma['code']}"}
            elif modules:
                last = await last_submission(user["id"], course["id"], None)
                text = ("Espera la corrección de tu evaluación final" if last and last["status"] == "en_revision"
                        else "Rinde la evaluación final del curso")
                next_step = {"text": text, "link": f"/curso/{course['id']}/final"}
            else:
                next_step = {"text": "El curso aún no tiene módulos publicados", "link": f"/curso/{course['id']}"}
        done = sum(1 for r in rows if r["state"] == "completado")
        out.append({"course_id": course["id"], "title": course["title"], "code": course.get("code", ""),
                    "progress": round(done / len(rows) * 100) if rows else 0, "modules": rows,
                    "final_passed": e["final_passed"], "next_step": next_step,
                    "grades": course_grades(e, course, modules)})
    return out


# ---------------- Cron: live class reminders ----------------
async def send_class_reminders():
    t = now()
    for c in await db.live_classes.find({"reminded": {"$ne": True}}, {"_id": 0}).to_list(1000):
        start = datetime.fromisoformat(c["start_at"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=t.tzinfo)
        mins = (start - t).total_seconds() / 60
        if mins > 40 or mins < 0:
            continue
        await db.live_classes.update_one({"id": c["id"]}, {"$set": {"reminded": True}})
        course = await db.courses.find_one({"id": c["course_id"]}, {"_id": 0, "title": 1}) or {"title": ""}
        ids = [e["user_id"] for e in await db.enrollments.find({"course_id": c["course_id"]}, {"user_id": 1}).to_list(5000)]
        hora = start.astimezone(ZoneInfo("America/Santiago")).strftime("%H:%M")
        platform = "Microsoft Teams" if c["platform"] == "teams" else "Google Meet"
        async for u in db.users.find({"id": {"$in": ids}, "active": True}, {"_id": 0}):
            try:
                await send_email(to=u["email"], subject=f"Recordatorio: {c['title']} comienza a las {hora}",
                                 html=class_reminder_html(u["nombre"], c["title"], course["title"], hora, platform))
            except Exception as ex:
                logger.error(f"Reminder email failed for {u['email']}: {ex}")
            await asyncio.sleep(0.6)


INACTIVE_DAYS = 7


async def last_activity(u):
    sess = await db.sessions.find({"user_id": u["id"]}, {"_id": 0, "last_seen": 1}).sort("last_seen", -1).to_list(1)
    stamps = [x for x in (u.get("last_login"), sess[0]["last_seen"] if sess else None) if x]
    return max(datetime.fromisoformat(x) for x in stamps) if stamps else None


async def send_inactivity_alerts():
    t = now()
    limit = t - timedelta(days=INACTIVE_DAYS)
    async for u in db.users.find({"role": "estudiante", "active": True}, {"_id": 0}):
        alerted = u.get("inactivity_alert_at")
        if alerted and datetime.fromisoformat(alerted) > limit:
            continue
        open_courses = await db.enrollments.find({"user_id": u["id"], "final_passed": False}, {"_id": 0}).to_list(100)
        if not open_courses:
            continue
        last = await last_activity(u)
        ref = last or min(datetime.fromisoformat(e["enrolled_at"]) for e in open_courses)
        if ref > limit:
            continue
        progress = [p for p in await my_progress(user=u) if not p["final_passed"]]
        if not progress:
            continue
        p = progress[0]
        days = (t - ref).days
        await db.users.update_one({"id": u["id"]}, {"$set": {"inactivity_alert_at": t.isoformat()}})
        try:
            await send_email(to=u["email"], subject=f"Te extrañamos en {EMAIL_FROM_NAME}: continúa tu curso",
                             html=inactivity_email_html(u["nombre"], days, p["title"], p["progress"], p["next_step"]["text"]))
        except Exception as ex:
            logger.error(f"Inactivity email failed for {u['email']}: {ex}")
        await asyncio.sleep(0.6)


async def accept_cron(request: Request) -> bool:
    """Validates cron auth; returns False for duplicate deliveries."""
    auth = request.headers.get("Authorization", "")
    secret = (await core.get_cfg())["cron_secret"]
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(401, "Unauthorized")
    run_id = request.headers.get("X-Webhook-Id")
    if not run_id:
        try:
            run_id = (await request.json()).get("run_id")
        except Exception:
            raise HTTPException(400, "Invalid body")
    if run_id:
        if await db.cron_runs.find_one({"run_id": run_id}):
            return False
        await db.cron_runs.insert_one({"run_id": run_id, "at": now_iso()})
    return True


@api.post("/cron/class-reminders")
async def cron_class_reminders(request: Request, bg: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not await accept_cron(request):
        return {"ok": True, "duplicate": True}
    bg.add_task(send_class_reminders)
    return {"ok": True}


@api.post("/cron/inactivity-alerts")
async def cron_inactivity_alerts(request: Request, bg: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not await accept_cron(request):
        return {"ok": True, "duplicate": True}
    bg.add_task(send_inactivity_alerts)
    return {"ok": True}


async def send_weekly_reports(recipients=None):
    courses = await db.courses.find({}, {"_id": 0, "id": 1}).sort("created_at", 1).to_list(500)
    reports = [await course_report(c["id"], None) for c in courses]
    if recipients is None:
        recipients = [u["email"] async for u in db.users.find({"role": "admin", "active": True}, {"_id": 0, "email": 1})]
    html = weekly_report_html(reports, now().astimezone(ZoneInfo("America/Santiago")).strftime("%d-%m-%Y"))
    for to in recipients:
        try:
            await send_email(to=to, subject=f"Reporte semanal OTEC – {EMAIL_FROM_NAME}", html=html)
        except Exception as ex:
            logger.error(f"Weekly report email failed for {to}: {ex}")
        await asyncio.sleep(0.6)


@api.post("/cron/weekly-report")
async def cron_weekly_report(request: Request, bg: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not await accept_cron(request):
        return {"ok": True, "duplicate": True}
    bg.add_task(send_weekly_reports)
    return {"ok": True}


# ---------------- Attendance certificates ----------------
@api.post("/live-classes/{class_id}/certificate")
async def attendance_certificate(class_id: str, user=Depends(get_current_user)):
    c = await db.live_classes.find_one({"id": class_id}, {"_id": 0})
    rec = await db.live_attendance.find_one({"class_id": class_id, "user_id": user["id"]}, {"_id": 0})
    if not c or not rec:
        raise HTTPException(404, "No registras asistencia a esta clase")
    if class_status(c) != "finalizada":
        raise HTTPException(400, "El certificado estará disponible cuando la clase finalice")
    code = rec.get("cert_code")
    if not code:
        code = "A" + secrets.token_hex(5).upper()
        await db.live_attendance.update_one({"class_id": class_id, "user_id": user["id"]},
                                            {"$set": {"cert_code": code, "cert_issued_at": now_iso()}})
    return {"code": code}


async def attendance_cert_data(code):
    rec = await db.live_attendance.find_one({"cert_code": code.upper()}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Certificado no encontrado")
    c = await db.live_classes.find_one({"id": rec["class_id"]}, {"_id": 0}) or {}
    u = await db.users.find_one({"id": rec["user_id"]}, {"_id": 0}) or {}
    course = await db.courses.find_one({"id": c.get("course_id")}, {"_id": 0, "title": 1}) or {}
    start, end = datetime.fromisoformat(c["start_at"]), datetime.fromisoformat(c["end_at"])
    return {"code": rec["cert_code"], "user_id": rec["user_id"],
            "student_name": f"{u.get('nombre', '')} {u.get('apellidos', '')}", "rut": u.get("rut", ""),
            "class_title": c.get("title"), "course_title": course.get("title", ""),
            "platform": "Microsoft Teams" if c.get("platform") == "teams" else "Google Meet",
            "start_at": c["start_at"], "end_at": c["end_at"], "joined_at": rec["joined_at"],
            "duration_min": round((end - start).total_seconds() / 60), "issued_at": rec.get("cert_issued_at")}


@api.get("/attendance-certificates/{code}")
async def get_attendance_certificate(code: str, user=Depends(get_current_user)):
    d = await attendance_cert_data(code)
    if user["role"] not in STAFF and d["user_id"] != user["id"]:
        raise HTTPException(403, "Sin permisos")
    return {**d, "otec_name": (await get_settings()).get("otec_name")}


@api.get("/public/verify-attendance/{code}")
async def verify_attendance(code: str):
    d = await attendance_cert_data(code)
    d.pop("user_id")
    return {**d, "valid": True, "otec_name": (await get_settings()).get("otec_name")}


# ---------------- OTEC course report ----------------
@api.get("/courses/{course_id}/report")
async def course_report(course_id: str, _=Depends(staff_only)):
    course = await db.courses.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(404, "Curso no encontrado")
    modules = await get_modules(course_id)
    class_ids = [c["id"] for c in await db.live_classes.find({"course_id": course_id}, {"_id": 0, "id": 1}).to_list(1000)]
    rows = []
    for e in await db.enrollments.find({"course_id": course_id}, {"_id": 0}).to_list(5000):
        u = await db.users.find_one({"id": e["user_id"]}, {"_id": 0})
        if not u:
            continue
        sess = await db.sessions.find({"user_id": u["id"]}, {"_id": 0, "duration_sec": 1}).to_list(5000)
        csess = await db.course_sessions.find({"user_id": u["id"], "course_id": course_id},
                                              {"_id": 0, "duration_sec": 1}).to_list(5000)
        live = await db.live_attendance.count_documents({"user_id": u["id"], "class_id": {"$in": class_ids}})
        g = course_grades(e, course, modules)
        done = len([m for m in modules if m["id"] in e["completed_modules"]])
        last = await last_activity(u)
        rows.append({"student_name": f"{u['nombre']} {u['apellidos']}", "nombre": u["nombre"], "apellidos": u["apellidos"],
                     "rut": u.get("rut", ""), "email": u["email"], "enrolled_at": e["enrolled_at"],
                     "method": e.get("method", ""), "last_access": last.isoformat() if last else None,
                     "days_attended": len(csess), "total_minutes": round(sum(x["duration_sec"] for x in csess) / 60),
                     "platform_days": len(sess), "platform_minutes": round(sum(x["duration_sec"] for x in sess) / 60),
                     "live_attended": live, "live_total": len(class_ids),
                     "live_pct": round(live / len(class_ids) * 100) if class_ids else None,
                     "modules_done": done, "modules_total": len(modules),
                     "progress": round(done / len(modules) * 100) if modules else 0,
                     "modules_avg_nota": g["modules_avg_nota"], "final_nota": g["final_nota"],
                     "overall_nota": g["overall_nota"],
                     "status": "Aprobado" if e["final_passed"] else "En curso", "completed_at": e.get("completed_at")})
    rows.sort(key=lambda r: r["student_name"].lower())
    return {"course": {"id": course["id"], "title": course["title"], "code": course.get("code", ""),
                       "hours": course.get("hours", 0)}, "generated_at": now_iso(), "rows": rows,
            "summary": {"students": len(rows), "approved": sum(r["status"] == "Aprobado" for r in rows),
                        "live_classes": len(class_ids)}}


# ---------------- Settings & diplomas ----------------
@api.get("/settings")
async def read_settings(_=Depends(get_current_user)):
    return await get_settings()


@api.put("/settings")
async def write_settings(body: SettingsIn, _=Depends(admin_only)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    for k in ("rector_signature", "vicerrector_signature", "directora_signature"):
        if upd.get(k):
            if not upd[k].startswith("data:image/png;base64,"):
                raise HTTPException(400, "La firma debe ser una imagen PNG")
            if len(upd[k]) > 1_500_000:
                raise HTTPException(400, "La imagen de la firma es demasiado grande (máx. 1 MB)")
    await db.settings.update_one({"id": "global"}, {"$set": {**(await get_settings()), **upd}}, upsert=True)
    return await get_settings()


@api.get("/my/diplomas")
async def my_diplomas(user=Depends(get_current_user)):
    return await db.diplomas.find({"user_id": user["id"]}, {"_id": 0, "pdf_path": 0}).sort("issued_at", -1).to_list(500)


@api.get("/diplomas")
async def all_diplomas(_=Depends(staff_only)):
    return await db.diplomas.find({}, {"_id": 0, "pdf_path": 0}).sort("issued_at", -1).to_list(5000)


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


async def build_certificate_pdf(d, s, verify_url):
    tpl = s.get("cert_template") or {}
    if tpl.get("file_id"):
        rec = await db.files.find_one({"id": tpl["file_id"]}, {"_id": 0})
        raw, ctype = await asyncio.to_thread(get_object, rec["storage_path"])
        png = await asyncio.to_thread(template_to_png, raw, rec["content_type"])
    else:
        png = DEFAULT_TEMPLATE.read_bytes()
    t = datetime.fromisoformat(d.get("approved_at") or now_iso()).astimezone(ZoneInfo("America/Santiago"))
    nota = d.get("nota_final")
    data = {"student_name": d["student_name"], "rut": d.get("rut", ""), "course_title": d["course_title"],
            "hours": d.get("hours", 0), "nota": f"{nota:.1f}".replace(".", ",") if nota else "",
            "date_text": f"Santiago, {t.day} de {MESES[t.month - 1]} de {t.year}", "code": d["code"],
            "verify_url": verify_url}
    sigs = [(s.get("rector_signature"), s.get("rector_name"), "Rector"),
            (s.get("vicerrector_signature"), s.get("vicerrector_name"), "Vicerrectora"),
            (s.get("directora_signature"), s.get("directora_name"), "Directora Académica")]
    return await asyncio.to_thread(render_certificate, png, data, s.get("cert_layout") or {}, sigs)


def app_base(request: Request):
    return f"https://{request.headers.get('x-forwarded-host') or request.headers.get('host')}"


MOTIVATION = [
    "El aprendizaje es el único tesoro que te acompañará a todas partes.",
    "Cada meta alcanzada es el punto de partida de un nuevo desafío. ¡Sigue creciendo!",
    "El éxito es la suma de pequeños esfuerzos repetidos día tras día.",
    "Invertir en conocimiento siempre paga el mejor interés.",
    "Hoy demostraste que con constancia todo es posible. ¡El próximo paso es tuyo!",
]


async def approve_one(d, base, admin_id, bg):
    d["approved_at"] = now_iso()
    s = await get_settings()
    pdf = await build_certificate_pdf(d, s, f"{base}/verificar/{d['code']}")
    res = await asyncio.to_thread(put_object, f"{APP_NAME}/certificados/{d['code']}.pdf", pdf, "application/pdf")
    upd = {"status": "aprobado", "approved_at": d["approved_at"], "approved_by": admin_id,
           "pdf_path": res["path"], "verify_url": f"{base}/verificar/{d['code']}", "reject_reason": ""}
    await db.diplomas.update_one({"id": d["id"]}, {"$set": upd})
    bg.add_task(notify_student_certificate, {**d, **upd})
    return {**d, **upd}


class BulkApproveIn(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=200)


@api.post("/diplomas/approve-bulk")
async def approve_bulk(body: BulkApproveIn, request: Request, bg: BackgroundTasks, admin=Depends(admin_only)):
    base, approved, errors = app_base(request), 0, []
    for d in await db.diplomas.find({"id": {"$in": body.ids}, "status": {"$ne": "aprobado"}}, {"_id": 0}).to_list(200):
        try:
            await approve_one(d, base, admin["id"], bg)
            approved += 1
        except Exception as ex:
            logger.error(f"Bulk approve failed for {d['id']}: {ex}")
            errors.append(d["student_name"])
    return {"approved": approved, "errors": errors}


@api.post("/diplomas/{diploma_id}/approve")
async def approve_diploma(diploma_id: str, request: Request, bg: BackgroundTasks, admin=Depends(admin_only)):
    d = await db.diplomas.find_one({"id": diploma_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Certificado no encontrado")
    if d.get("status") == "aprobado":
        raise HTTPException(400, "Este certificado ya fue aprobado")
    try:
        return await approve_one(d, app_base(request), admin["id"], bg)
    except Exception as ex:
        logger.error(f"Certificate render failed: {ex}")
        raise HTTPException(500, "No se pudo generar el PDF. Revisa la plantilla en Configuración.")


async def notify_student_certificate(d):
    u = await db.users.find_one({"id": d["user_id"]}, {"_id": 0})
    try:
        await send_email(to=u["email"], subject=f"¡Felicidades! Completaste {d['course_title']} – {EMAIL_FROM_NAME}",
                         html=cert_approved_email_html(u["nombre"], d["course_title"], d.get("nota_final"), d["code"],
                                                       d["verify_url"], secrets.choice(MOTIVATION)))
    except Exception as ex:
        logger.error(f"Certificate email failed: {ex}")


@api.post("/diplomas/{diploma_id}/reject")
async def reject_diploma(diploma_id: str, body: RejectIn, _=Depends(admin_only)):
    d = await db.diplomas.find_one({"id": diploma_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Certificado no encontrado")
    if d.get("status") == "aprobado":
        raise HTTPException(400, "No se puede rechazar un certificado ya emitido")
    await db.diplomas.update_one({"id": diploma_id}, {"$set": {"status": "rechazado", "reject_reason": body.reason}})
    return {"ok": True}


async def certificate_pdf_response(d):
    if d.get("status") != "aprobado" or not d.get("pdf_path"):
        raise HTTPException(404, "Certificado aún no emitido")
    data, _ct = await asyncio.to_thread(get_object, d["pdf_path"])
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="certificado_{d["code"]}.pdf"'})


@api.get("/diplomas/{code}/pdf")
async def diploma_pdf(code: str, user=Depends(get_current_user)):
    d = await db.diplomas.find_one({"code": code.upper()}, {"_id": 0})
    if not d or (user["role"] not in STAFF and d["user_id"] != user["id"]):
        raise HTTPException(404, "Certificado no encontrado")
    return await certificate_pdf_response(d)


@api.get("/public/diplomas/{code}/pdf")
async def public_diploma_pdf(code: str):
    d = await db.diplomas.find_one({"code": code.upper()}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Certificado no encontrado")
    return await certificate_pdf_response(d)


@api.post("/settings/certificate-preview")
async def certificate_preview(request: Request, _=Depends(admin_only)):
    s = await get_settings()
    sample = {"student_name": "María José González Pérez", "rut": "12.345.678-9", "hours": 40, "nota_final": 6.2,
              "course_title": "Nombre del curso de ejemplo para la vista previa", "code": "IBA-XXXX-XXXX"}
    try:
        pdf = await build_certificate_pdf(sample, s, f"{app_base(request)}/verificar/IBA-XXXX-XXXX")
    except Exception as ex:
        logger.error(f"Certificate preview failed: {ex}")
        raise HTTPException(400, "No se pudo usar la plantilla. Sube un PNG, JPG o PDF válido.")
    return Response(content=pdf, media_type="application/pdf")


async def diploma_with_settings(code):
    d = await db.diplomas.find_one({"code": code.upper()}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Diploma no encontrado")
    s = await get_settings()
    return d, s


@api.get("/diplomas/{code}")
async def get_diploma(code: str, user=Depends(get_current_user)):
    d, s = await diploma_with_settings(code)
    if user["role"] not in STAFF and d["user_id"] != user["id"]:
        raise HTTPException(403, "Sin permisos")
    d.pop("pdf_path", None)
    return {**d, "settings": {"otec_name": s.get("otec_name")}}


@api.get("/public/verify/{code}")
async def verify_diploma(code: str):
    d, s = await diploma_with_settings(code)
    if d.get("status") != "aprobado":
        raise HTTPException(404, "Diploma no encontrado")
    return {"valid": True, "code": d["code"], "student_name": d["student_name"], "rut": d.get("rut", ""),
            "nota_final": d.get("nota_final"), "approved_at": d.get("approved_at"),
            "course_title": d["course_title"], "hours": d.get("hours", 0), "issued_at": d["issued_at"],
            "otec_name": s.get("otec_name")}


# ---------------- Files (object storage) ----------------
MAX_FILE = 100 * 1024 * 1024
ALLOWED_EXT = {"pdf", "ppt", "pptx", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "gif", "webp",
               "mp4", "webm", "mov", "mp3", "txt", "zip"}


@api.post("/files")
async def upload_file(file: UploadFile = File(...), user=Depends(staff_only)):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Tipo de archivo no permitido")
    data = await file.read()
    if len(data) > MAX_FILE:
        raise HTTPException(400, "El archivo supera 100 MB")
    ctype = file.content_type or "application/octet-stream"
    result = await asyncio.to_thread(put_object, f"{APP_NAME}/uploads/{user['id']}/{new_id()}.{ext}", data, ctype)
    doc = {"id": new_id(), "storage_path": result["path"], "original_filename": file.filename, "content_type": ctype,
           "size": len(data), "is_deleted": False, "uploaded_by": user["id"], "created_at": now_iso()}
    await db.files.insert_one(doc)
    return {"id": doc["id"], "file_name": file.filename, "content_type": ctype, "size": len(data)}


@api.get("/files/{file_id}")
async def download_file(file_id: str, _=Depends(get_current_user)):
    rec = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Archivo no encontrado")
    data, _ct = await asyncio.to_thread(get_object, rec["storage_path"])
    disp = "inline" if rec["content_type"].startswith(("image/", "video/", "audio/")) or rec["content_type"] == "application/pdf" else "attachment"
    safe = rec["original_filename"].encode("ascii", "ignore").decode().replace('"', "")
    return Response(content=data, media_type=rec["content_type"],
                    headers={"Content-Disposition": f'{disp}; filename="{safe}"'})


OFFICE_EXT = (".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx")


@api.get("/files/{file_id}/viewer-url")
async def file_viewer_url(file_id: str, request: Request, _=Depends(get_current_user)):
    rec = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not rec or not rec["original_filename"].lower().endswith(OFFICE_EXT):
        raise HTTPException(404, "Archivo no encontrado")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    ext = rec["original_filename"].rsplit(".", 1)[-1].lower()
    return {"url": f"https://{host}/api/public/files/{create_file_token(file_id)}/file.{ext}"}


@api.get("/public/files/{token}/{name}")
async def public_file(token: str, name: str):
    file_id = read_file_token(token)
    if not file_id:
        raise HTTPException(403, "Enlace expirado")
    rec = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Archivo no encontrado")
    data, _ct = await asyncio.to_thread(get_object, rec["storage_path"])
    return Response(content=data, media_type=rec["content_type"])


@api.get("/")
async def root():
    return {"message": "OTEC API"}


from shop import router as shop_router  # noqa: E402
from integrations import router as integrations_router  # noqa: E402
from messaging import router as messaging_router  # noqa: E402
from importer import router as importer_router  # noqa: E402

api.include_router(shop_router)
api.include_router(integrations_router)
api.include_router(messaging_router)
api.include_router(importer_router)
app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True,
                   allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.otp_codes.create_index("expires_at", expireAfterSeconds=0)
    await db.diplomas.create_index("code", unique=True)
    await db.sessions.create_index([("user_id", 1), ("date", 1)])
    await db.course_sessions.create_index([("user_id", 1), ("course_id", 1), ("date", 1)])
    await db.module_sessions.create_index([("user_id", 1), ("module_id", 1)])
    try:
        await asyncio.to_thread(init_storage)
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    meta = await db.app_meta.find_one({"id": "public"})
    if meta:
        core.PUBLIC_BASE = meta["base"]
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    if not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one({"id": new_id(), "email": admin_email, "nombre": "Administrador", "apellidos": "OTEC",
                                   "rut": "", "role": "admin", "active": True, "created_at": now_iso(),
                                   "last_login": None, "signup_method": "seed"})
    else:
        await db.users.update_one({"email": admin_email}, {"$set": {"role": "admin", "active": True}})


@app.on_event("shutdown")
async def shutdown():
    client.close()
