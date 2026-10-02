import csv
import io
import random
import secrets
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from core import (db, client, now, now_iso, new_id, create_token, get_current_user, require_roles,
                  send_email, otp_email_html, analyze_ai_usage, EMAIL_FROM_NAME)
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
    type: Literal["mc", "open"] = "mc"
    text: str
    options: List[str] = []
    correct: Optional[int] = None


class Quiz(BaseModel):
    questions: List[Question] = []
    pass_score: int = 60


class CourseIn(BaseModel):
    title: str
    description: str = ""
    code: str = ""
    hours: int = 0
    auto_enroll: bool = False
    published: bool = True


class ModuleIn(BaseModel):
    title: str
    description: str = ""
    content: str = ""
    video_url: str = ""
    order: Optional[int] = None
    quiz: Quiz = Quiz()


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
    return doc


async def auto_enroll(user_id):
    async for c in db.courses.find({"auto_enroll": True, "published": True}, {"_id": 0, "id": 1}):
        await enroll(user_id, c["id"], "automatica")


async def get_modules(course_id):
    return await db.modules.find({"course_id": course_id}, {"_id": 0}).sort("order", 1).to_list(500)


def strip_answers(quiz):
    qs = [{k: v for k, v in q.items() if k != "correct"} for q in (quiz or {}).get("questions", [])]
    return {"questions": qs, "pass_score": (quiz or {}).get("pass_score", 60)}


def grade(quiz, answers):
    qs = quiz.get("questions", [])
    mc = [q for q in qs if q["type"] == "mc"]
    opens = [q for q in qs if q["type"] == "open"]
    correct = sum(1 for q in mc if str(answers.get(q["id"])) == str(q.get("correct")))
    open_ok = all(str(answers.get(q["id"], "")).strip() for q in opens)
    score = round(correct / len(mc) * 100) if mc else (100 if open_ok else 0)
    passed = score >= quiz.get("pass_score", 60) and open_ok
    return score, passed


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


async def issue_diploma(user, course):
    existing = await db.diplomas.find_one({"user_id": user["id"], "course_id": course["id"]}, {"_id": 0})
    if existing:
        return existing
    doc = {"id": new_id(), "code": secrets.token_hex(6).upper(), "user_id": user["id"], "course_id": course["id"],
           "student_name": f"{user['nombre']} {user['apellidos']}", "rut": user.get("rut", ""),
           "course_title": course["title"], "hours": course.get("hours", 0), "issued_at": now_iso()}
    await db.diplomas.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_settings():
    s = await db.settings.find_one({"id": "global"}, {"_id": 0})
    return s or {"id": "global", "otec_name": EMAIL_FROM_NAME, "rector_name": "", "vicerrector_name": "",
                 "rector_signature": "", "vicerrector_signature": ""}


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
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return public_user(user)


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


# ---------------- Activity (attendance / permanence) ----------------
@api.post("/activity/heartbeat")
async def heartbeat(user=Depends(get_current_user)):
    t = now()
    date = t.date().isoformat()
    sess = await db.sessions.find_one({"user_id": user["id"], "date": date})
    if sess:
        gap = (t - datetime.fromisoformat(sess["last_seen"])).total_seconds()
        add = int(min(max(gap, 0), 90))
        await db.sessions.update_one({"_id": sess["_id"]}, {"$set": {"last_seen": t.isoformat()},
                                                            "$inc": {"duration_sec": add}})
    else:
        await db.sessions.insert_one({"id": new_id(), "user_id": user["id"], "date": date,
                                      "started_at": t.isoformat(), "last_seen": t.isoformat(), "duration_sec": 0})
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
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
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


@api.get("/modules/{module_id}")
async def get_module(module_id: str, user=Depends(get_current_user)):
    m, _ = await accessible_module(module_id, user)
    if user["role"] not in STAFF:
        m["quiz"] = strip_answers(m.get("quiz"))
        last = await db.submissions.find({"user_id": user["id"], "module_id": module_id},
                                         {"_id": 0, "score": 1, "passed": 1, "created_at": 1}).sort("created_at", -1).to_list(1)
        m["last_submission"] = last[0] if last else None
    return m


@api.post("/modules/{module_id}/complete")
async def complete_module(module_id: str, user=Depends(get_current_user)):
    m, e = await accessible_module(module_id, user)
    if not e:
        raise HTTPException(400, "Solo estudiantes")
    if m.get("quiz", {}).get("questions"):
        raise HTTPException(400, "Este módulo requiere aprobar la evaluación")
    await db.enrollments.update_one({"id": e["id"]}, {"$addToSet": {"completed_modules": module_id}})
    return {"ok": True}


async def save_submission(user, course_id, module_id, quiz, body: SubmitIn, bg: BackgroundTasks):
    score, passed = grade(quiz, body.answers)
    sub = {"id": new_id(), "user_id": user["id"], "student_name": f"{user['nombre']} {user['apellidos']}",
           "course_id": course_id, "module_id": module_id, "kind": "final" if module_id is None else "modulo",
           "questions": quiz["questions"], "answers": body.answers, "score": score, "passed": passed,
           "behavior": {"tab_switches": body.tab_switches, "paste_events": body.paste_events,
                        "duration_sec": body.duration_sec},
           "ai_status": "pendiente", "ai_analysis": None, "created_at": now_iso()}
    await db.submissions.insert_one(sub)
    bg.add_task(run_ai_analysis, sub["id"])
    return sub


@api.post("/modules/{module_id}/submit")
async def submit_module(module_id: str, body: SubmitIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    m, e = await accessible_module(module_id, user)
    if not e:
        raise HTTPException(400, "Solo estudiantes")
    if not m.get("quiz", {}).get("questions"):
        raise HTTPException(400, "Este módulo no tiene evaluación")
    sub = await save_submission(user, m["course_id"], module_id, m["quiz"], body, bg)
    if sub["passed"]:
        await db.enrollments.update_one({"id": e["id"]}, {"$addToSet": {"completed_modules": module_id}})
    return {"score": sub["score"], "passed": sub["passed"], "pass_score": m["quiz"]["pass_score"]}


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
        raise HTTPException(403, "Debes completar todos los módulos")
    return {**strip_answers(course["final_exam"]), "course_title": course["title"], "final_passed": e["final_passed"]}


@api.post("/courses/{course_id}/final-exam/submit")
async def submit_final(course_id: str, body: SubmitIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    course = await db.courses.find_one({"id": course_id}, {"_id": 0})
    e = await require_enrollment(user, course_id)
    modules = await get_modules(course_id)
    if not modules or not all(m["id"] in e["completed_modules"] for m in modules):
        raise HTTPException(403, "Debes completar todos los módulos")
    if not course["final_exam"]["questions"]:
        raise HTTPException(400, "El curso aún no tiene evaluación final")
    sub = await save_submission(user, course_id, None, course["final_exam"], body, bg)
    diploma = None
    if sub["passed"]:
        await db.enrollments.update_one({"id": e["id"]}, {"$set": {"final_passed": True, "completed_at": now_iso()}})
        diploma = await issue_diploma(user, course)
    return {"score": sub["score"], "passed": sub["passed"], "pass_score": course["final_exam"]["pass_score"],
            "diploma_code": diploma["code"] if diploma else None}


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
    rows = await db.live_attendance.find({"class_id": class_id}, {"_id": 0}).to_list(5000)
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": [r["user_id"] for r in rows]}}, {"_id": 0}).to_list(5000)}
    return [{"student_name": f"{users.get(r['user_id'], {}).get('nombre', '')} {users.get(r['user_id'], {}).get('apellidos', '')}",
             "email": users.get(r["user_id"], {}).get("email"), "joined_at": r["joined_at"]} for r in rows]


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
        subs = await db.submissions.find({"user_id": s["id"]}, {"_id": 0, "score": 1, "ai_analysis": 1}).to_list(1000)
        progs = [round(len(e["completed_modules"]) / mod_counts[e["course_id"]] * 100) for e in ens if mod_counts.get(e["course_id"])]
        ai = [x["ai_analysis"]["percentage"] for x in subs if x.get("ai_analysis")]
        out.append({**public_user(s),
                    "days_attended": len(sess),
                    "total_minutes": round(sum(x["duration_sec"] for x in sess) / 60),
                    "logins": await db.access_logs.count_documents({"user_id": s["id"]}),
                    "courses": len(ens),
                    "progress": round(sum(progs) / len(progs)) if progs else 0,
                    "avg_score": round(sum(x["score"] for x in subs) / len(subs)) if subs else None,
                    "ai_avg": round(sum(ai) / len(ai)) if ai else None})
    return out


# ---------------- Settings & diplomas ----------------
@api.get("/settings")
async def read_settings(_=Depends(get_current_user)):
    return await get_settings()


@api.put("/settings")
async def write_settings(body: SettingsIn, _=Depends(admin_only)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    for k in ("rector_signature", "vicerrector_signature"):
        if upd.get(k):
            if not upd[k].startswith("data:image/png;base64,"):
                raise HTTPException(400, "La firma debe ser una imagen PNG")
            if len(upd[k]) > 1_500_000:
                raise HTTPException(400, "La imagen de la firma es demasiado grande (máx. 1 MB)")
    await db.settings.update_one({"id": "global"}, {"$set": {**(await get_settings()), **upd}}, upsert=True)
    return await get_settings()


@api.get("/my/diplomas")
async def my_diplomas(user=Depends(get_current_user)):
    return await db.diplomas.find({"user_id": user["id"]}, {"_id": 0}).sort("issued_at", -1).to_list(500)


@api.get("/diplomas")
async def all_diplomas(_=Depends(staff_only)):
    return await db.diplomas.find({}, {"_id": 0}).sort("issued_at", -1).to_list(5000)


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
    return {**d, "settings": s}


@api.get("/public/verify/{code}")
async def verify_diploma(code: str):
    d, s = await diploma_with_settings(code)
    return {"valid": True, "code": d["code"], "student_name": d["student_name"], "rut": d.get("rut", ""),
            "course_title": d["course_title"], "hours": d.get("hours", 0), "issued_at": d["issued_at"],
            "otec_name": s.get("otec_name")}


@api.get("/")
async def root():
    return {"message": "OTEC API"}


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
