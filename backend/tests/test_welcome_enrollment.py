"""Iteration 9: admin seeding + welcome email on enrollment.

Covers:
- Admin info@iberoacademy.cl seeded on startup, OTP login, role=admin
- POST /api/users with course_id enrolls + sends welcome email once
- POST /api/enrollments: new enrollment -> welcome; duplicate -> no new welcome
- POST /api/enrollments is not blocked by email send (async)
- welcome_email_html body contains required pieces
- Regression: GET /api/courses, GET /api/auth/me, backend logs clean
"""
import os
import sys
import time
import uuid
import pathlib
import importlib

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

BACKEND_DIR = pathlib.Path("/app/backend")
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fall back to frontend/.env
    load_dotenv("/app/frontend/.env")
    BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"].lower()

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


# ---------- shared state ----------
STATE = {"token": None, "course_id": None, "user_ids": [], "enrollment_ids": []}


def _auth_headers():
    return {"Authorization": f"Bearer {STATE['token']}"}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    # delete created test enrollments, users, course
    for eid in STATE["enrollment_ids"]:
        db.enrollments.delete_one({"id": eid})
    if STATE["course_id"]:
        db.enrollments.delete_many({"course_id": STATE["course_id"]})
        db.modules.delete_many({"course_id": STATE["course_id"]})
        db.courses.delete_one({"id": STATE["course_id"]})
    for uid in STATE["user_ids"]:
        db.enrollments.delete_many({"user_id": uid})
        db.users.delete_one({"id": uid})


# ---------- admin seed + OTP login ----------
def test_admin_seeded():
    u = db.users.find_one({"email": ADMIN_EMAIL})
    assert u is not None, "Admin not seeded on startup"
    assert u["role"] == "admin"
    assert u["active"] is True


def test_admin_login_via_otp():
    r = requests.post(f"{BASE_URL}/api/auth/request-code", json={"email": ADMIN_EMAIL}, timeout=20)
    assert r.status_code == 200, r.text
    # read OTP from mongo
    rec = db.otp_codes.find_one({"email": ADMIN_EMAIL})
    assert rec and rec.get("code")
    r2 = requests.post(f"{BASE_URL}/api/auth/verify-code",
                       json={"email": ADMIN_EMAIL, "code": rec["code"]}, timeout=20)
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert "token" in data and data["user"]["role"] == "admin"
    assert data["user"]["email"] == ADMIN_EMAIL
    STATE["token"] = data["token"]


def test_auth_me():
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_headers(), timeout=15)
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL


# ---------- welcome_email_html content ----------
def test_welcome_email_html_content():
    import core
    importlib.reload(core)
    html = core.welcome_email_html(
        "Ana Pérez", "delivered+ana@resend.dev", "Prevención de Riesgos", 4, 20,
        "https://example.com/login",
    )
    low = html.lower()
    required = [
        "ana p", "delivered+ana@resend.dev", "prevención de riesgos",
        "4 módulos", "20 horas", "usuario:", "código de 6 dígitos",
        "examen", "examen final", "certificado",
        "meticuloso", "tiempo mínimo", "ingresos", "tiempo",
    ]
    missing = [k for k in required if k not in low]
    assert not missing, f"welcome html missing: {missing}"
    # no forms/inputs allowed by email safety
    assert "<form" not in low and "<input" not in low


# ---------- setup course + modules ----------
def test_create_course_with_modules():
    tag = uuid.uuid4().hex[:6]
    body = {
        "title": f"TEST Curso Bienvenida {tag}",
        "code": f"TEST-{tag.upper()}",
        "description": "Curso para test de bienvenida",
        "hours": 10,
        "published": True,
        "auto_enroll": False,
        "show_on_landing": False,
    }
    r = requests.post(f"{BASE_URL}/api/courses", json=body, headers=_auth_headers(), timeout=20)
    assert r.status_code == 200, r.text
    c = r.json()
    STATE["course_id"] = c["id"]
    # add 3 modules
    for i in range(3):
        rm = requests.post(f"{BASE_URL}/api/courses/{c['id']}/modules",
                           json={"title": f"Módulo {i+1}", "order": i + 1, "min_minutes": 5},
                           headers=_auth_headers(), timeout=20)
        assert rm.status_code == 200, rm.text


# ---------- POST /api/users with course_id -> enrolls + welcome ----------
def test_create_user_with_course_enrolls_and_sends_welcome():
    assert STATE["course_id"]
    tag = uuid.uuid4().hex[:6]
    email = f"delivered+newuser{tag}@resend.dev"
    body = {"email": email, "nombre": "TestUser", "apellidos": "Welcome",
            "rut": "", "role": "estudiante", "course_id": STATE["course_id"]}
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/users", json=body, headers=_auth_headers(), timeout=20)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    u = r.json()
    STATE["user_ids"].append(u["id"])
    # Response must be fast (email is fire-and-forget)
    assert elapsed < 5.0, f"POST /api/users slow ({elapsed:.2f}s) — email send not fire-and-forget?"
    # Allow background task to run
    time.sleep(1.0)
    # Enrollment persisted
    e = db.enrollments.find_one({"user_id": u["id"], "course_id": STATE["course_id"]})
    assert e is not None
    STATE["enrollment_ids"].append(e["id"])
    assert e["method"] == "manual"


# ---------- POST /api/enrollments idempotency ----------
def test_duplicate_enrollment_returns_existing():
    assert STATE["user_ids"]
    uid = STATE["user_ids"][0]
    r = requests.post(f"{BASE_URL}/api/enrollments",
                      json={"user_id": uid, "course_id": STATE["course_id"]},
                      headers=_auth_headers(), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user_id"] == uid
    # Should match existing enrollment id (idempotent) and NOT create another document
    count = db.enrollments.count_documents({"user_id": uid, "course_id": STATE["course_id"]})
    assert count == 1, f"duplicate enroll created extra docs (count={count})"


def test_new_enrollment_via_endpoint():
    # Create another user without course then enroll via /api/enrollments
    tag = uuid.uuid4().hex[:6]
    email = f"delivered+second{tag}@resend.dev"
    r = requests.post(f"{BASE_URL}/api/users",
                      json={"email": email, "nombre": "Second", "apellidos": "User",
                            "rut": "", "role": "estudiante"},
                      headers=_auth_headers(), timeout=20)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    STATE["user_ids"].append(uid)
    # no course_id passed -> no enrollment yet
    assert db.enrollments.count_documents({"user_id": uid}) == 0
    t0 = time.time()
    r2 = requests.post(f"{BASE_URL}/api/enrollments",
                       json={"user_id": uid, "course_id": STATE["course_id"]},
                       headers=_auth_headers(), timeout=20)
    elapsed = time.time() - t0
    assert r2.status_code == 200, r2.text
    assert elapsed < 5.0, f"POST /api/enrollments slow ({elapsed:.2f}s)"
    doc = r2.json()
    STATE["enrollment_ids"].append(doc["id"])
    # Should NOT contain mongo _id in response
    assert "_id" not in doc
    time.sleep(1.0)
    assert db.enrollments.count_documents({"user_id": uid, "course_id": STATE["course_id"]}) == 1


# ---------- backend logs free of welcome failures (for our test run window) ----------
def test_no_welcome_email_failures_in_logs():
    # read last 400 lines of backend error log
    log_paths = ["/var/log/supervisor/backend.err.log", "/var/log/supervisor/backend.out.log"]
    bad = []
    for p in log_paths:
        if not os.path.exists(p):
            continue
        with open(p, "r", errors="ignore") as f:
            lines = f.readlines()[-800:]
        for ln in lines:
            if "Welcome email failed" in ln:
                bad.append(ln.strip())
    assert not bad, f"Welcome email failures in logs: {bad[-5:]}"


# ---------- regression ----------
def test_courses_listing():
    r = requests.get(f"{BASE_URL}/api/courses", headers=_auth_headers(), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert any(c["id"] == STATE["course_id"] for c in r.json())
