"""Iteration 10: admin mass-messaging (templates + campaigns).

Covers:
- Admin-only: /api/admin/templates, /api/admin/messages/* return 401/403 for non-admin/students
- GET /api/admin/templates seeds 4 defaults once (deleting one does NOT re-seed)
- Create / update / delete templates
- POST /api/admin/messages/preview returns count, html with variables substituted,
  links rendered as <a>, HTML in body escaped
- POST /api/admin/messages/test (delivered@resend.dev)
- POST /api/admin/messages/send with audience=course containing ONLY test users
  -> campaign goes enviando -> completado with sent=2
"""
import os
import sys
import time
import pathlib

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

BACKEND_DIR = pathlib.Path("/app/backend")
load_dotenv(BACKEND_DIR / ".env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"].lower()

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]

STATE = {
    "admin_token": None,
    "student_token": None,
    "course_id": None,
    "user_ids": [],
    "enrollment_ids": [],
    "campaign_ids": [],
    "created_template_ids": [],
    "student_email": None,
}


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- cleanup ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for cid in STATE["campaign_ids"]:
        db.campaigns.delete_one({"id": cid})
    for tid in STATE["created_template_ids"]:
        db.email_templates.delete_one({"id": tid})
    if STATE["course_id"]:
        db.enrollments.delete_many({"course_id": STATE["course_id"]})
        db.modules.delete_many({"course_id": STATE["course_id"]})
        db.courses.delete_one({"id": STATE["course_id"]})
    for uid in STATE["user_ids"]:
        db.enrollments.delete_many({"user_id": uid})
        db.users.delete_one({"id": uid})


# ---------- auth helpers ----------
def _otp_login(email: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/request-code", json={"email": email}, timeout=20)
    assert r.status_code == 200, r.text
    rec = db.otp_codes.find_one({"email": email.lower()})
    assert rec and rec.get("code"), f"OTP not found for {email}"
    r2 = requests.post(f"{BASE_URL}/api/auth/verify-code",
                       json={"email": email, "code": rec["code"]}, timeout=20)
    assert r2.status_code == 200, r2.text
    return r2.json()["token"]


def test_admin_login():
    STATE["admin_token"] = _otp_login(ADMIN_EMAIL)


# ---------- Create TEST course + 2 students, enroll them ----------
def test_setup_course_and_students():
    tok = STATE["admin_token"]
    # Create course
    r = requests.post(f"{BASE_URL}/api/courses",
                      headers=_h(tok),
                      json={"title": "TEST Mensajes Course",
                            "description": "test",
                            "modules": [{"title": "M1", "hours": 1, "content": "c"}]},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    STATE["course_id"] = cid

    for i in range(2):
        email = f"delivered+msgtest{i}@resend.dev"
        r = requests.post(f"{BASE_URL}/api/users",
                          headers=_h(tok),
                          json={"email": email, "nombre": f"Test{i}", "apellidos": "User",
                                "rut": f"1111111{i}-1", "role": "estudiante",
                                "course_id": cid},
                          timeout=20)
        assert r.status_code in (200, 201), r.text
        STATE["user_ids"].append(r.json()["id"])
        if i == 0:
            STATE["student_email"] = email

    # Confirm enrollments
    count = db.enrollments.count_documents({"course_id": cid})
    assert count == 2, f"Expected 2 enrollments, got {count}"


# ---------- Admin-only guards ----------
def test_templates_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/templates", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


def test_messages_endpoints_require_auth():
    for path, method in [("/api/admin/messages/preview", "post"),
                         ("/api/admin/messages/test", "post"),
                         ("/api/admin/messages/send", "post"),
                         ("/api/admin/messages/campaigns", "get")]:
        if method == "get":
            r = requests.get(f"{BASE_URL}{path}", timeout=15)
        else:
            r = requests.post(f"{BASE_URL}{path}", json={}, timeout=15)
        assert r.status_code in (401, 403), f"{path} returned {r.status_code}"


def test_student_cannot_access_admin_endpoints():
    STATE["student_token"] = _otp_login(STATE["student_email"])
    tok = STATE["student_token"]
    r = requests.get(f"{BASE_URL}/api/admin/templates", headers=_h(tok), timeout=15)
    assert r.status_code == 403, f"student should get 403 got {r.status_code}"
    r = requests.get(f"{BASE_URL}/api/admin/messages/campaigns", headers=_h(tok), timeout=15)
    assert r.status_code == 403


# ---------- Templates CRUD + seed-once ----------
def test_templates_seeded_four_defaults():
    tok = STATE["admin_token"]
    r = requests.get(f"{BASE_URL}/api/admin/templates", headers=_h(tok), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    names = [t["name"] for t in data]
    for expected in ["Bienvenida", "Recordatorio de avance",
                     "Nuevo curso disponible", "Aviso general"]:
        assert expected in names, f"Default template '{expected}' missing. Got: {names}"
    # No mongo _id leak
    for t in data:
        assert "_id" not in t


def test_delete_one_default_does_not_reseed():
    tok = STATE["admin_token"]
    r = requests.get(f"{BASE_URL}/api/admin/templates", headers=_h(tok), timeout=15)
    data = r.json()
    target = next(t for t in data if t["name"] == "Aviso general")
    tid = target["id"]
    # Delete it
    r = requests.delete(f"{BASE_URL}/api/admin/templates/{tid}", headers=_h(tok), timeout=15)
    assert r.status_code == 200
    # Fetch again
    r = requests.get(f"{BASE_URL}/api/admin/templates", headers=_h(tok), timeout=15)
    names = [t["name"] for t in r.json()]
    assert "Aviso general" not in names, "Deleted default should NOT be re-seeded"
    # Restore to not pollute env
    requests.post(f"{BASE_URL}/api/admin/templates", headers=_h(tok),
                  json={"name": target["name"], "subject": target["subject"],
                        "body": target["body"]}, timeout=15)


def test_create_update_delete_template():
    tok = STATE["admin_token"]
    r = requests.post(f"{BASE_URL}/api/admin/templates", headers=_h(tok),
                      json={"name": "TEST tpl", "subject": "Hola {nombre}",
                            "body": "Hola {nombre}, visita [sitio](https://example.com)."},
                      timeout=15)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    STATE["created_template_ids"].append(tid)
    assert r.json()["name"] == "TEST tpl"
    assert "_id" not in r.json()

    # Update
    r = requests.put(f"{BASE_URL}/api/admin/templates/{tid}", headers=_h(tok),
                     json={"name": "TEST tpl v2", "subject": "s", "body": "b"},
                     timeout=15)
    assert r.status_code == 200
    assert r.json()["name"] == "TEST tpl v2"
    assert db.email_templates.find_one({"id": tid})["name"] == "TEST tpl v2"

    # Delete
    r = requests.delete(f"{BASE_URL}/api/admin/templates/{tid}", headers=_h(tok), timeout=15)
    assert r.status_code == 200
    assert db.email_templates.find_one({"id": tid}) is None
    STATE["created_template_ids"].remove(tid)


# ---------- Preview ----------
def test_preview_all_audiences_counts_and_render():
    tok = STATE["admin_token"]
    body = ("Hola {nombre} {apellidos}, tu correo es {email}, curso: {curso}. "
            "Visita [aqu\u00ed](https://example.com) y <script>alert(1)</script>")
    msg = {"subject": "Hola {nombre}", "body": body,
           "audience": {"type": "course", "course_id": STATE["course_id"], "days": 7}}
    r = requests.post(f"{BASE_URL}/api/admin/messages/preview",
                      headers=_h(tok), json=msg, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 2, f"course audience should see 2, got {data['count']}"
    html = data["html"]
    assert "Hola Test0" in data["subject"] or "Hola Test1" in data["subject"]
    # variable substitution happened
    assert "Test0" in html or "Test1" in html
    assert "@resend.dev" in html
    assert "TEST Mensajes Course" in html
    # markdown link rendered as <a>
    assert '<a href="https://example.com"' in html
    # HTML in body escaped
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html

    # audience=students: must be >= 1 (at least our 2 test users)
    r = requests.post(f"{BASE_URL}/api/admin/messages/preview",
                      headers=_h(tok),
                      json={"subject": "s", "body": "b",
                            "audience": {"type": "students"}},
                      timeout=20)
    assert r.status_code == 200
    assert r.json()["count"] >= 2

    # audience=all: >= students
    r = requests.post(f"{BASE_URL}/api/admin/messages/preview",
                      headers=_h(tok),
                      json={"subject": "s", "body": "b",
                            "audience": {"type": "all"}},
                      timeout=20)
    assert r.status_code == 200
    assert r.json()["count"] >= 2

    # audience=inactive with days=1
    r = requests.post(f"{BASE_URL}/api/admin/messages/preview",
                      headers=_h(tok),
                      json={"subject": "s", "body": "b",
                            "audience": {"type": "inactive", "days": 1}},
                      timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json()["count"], int)


# ---------- Test email ----------
def test_send_test_email():
    tok = STATE["admin_token"]
    r = requests.post(f"{BASE_URL}/api/admin/messages/test",
                      headers=_h(tok),
                      json={"subject": "Prueba {nombre}",
                            "body": "Hola {nombre}, [link](https://example.com)",
                            "to": "delivered@resend.dev",
                            "audience": {"type": "students"}},
                      timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


# ---------- Mass send (course audience only) ----------
def test_send_campaign_course_audience():
    tok = STATE["admin_token"]
    msg = {"subject": "TEST campaign {nombre}",
           "body": "Hola {nombre}, bienvenido a {curso}.",
           "audience": {"type": "course", "course_id": STATE["course_id"], "days": 7}}
    r = requests.post(f"{BASE_URL}/api/admin/messages/send",
                      headers=_h(tok), json=msg, timeout=20)
    assert r.status_code == 200, r.text
    camp = r.json()
    assert camp["status"] == "enviando"
    assert camp["total"] == 2
    assert "_id" not in camp
    cid = camp["id"]
    STATE["campaign_ids"].append(cid)

    # Poll campaigns list for completion (0.6s per recipient => ~1.2s, give 10s)
    completed = None
    deadline = time.time() + 15
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/admin/messages/campaigns",
                         headers=_h(tok), timeout=15)
        assert r.status_code == 200
        items = r.json()
        found = next((c for c in items if c["id"] == cid), None)
        assert found is not None
        if found["status"] == "completado":
            completed = found
            break
        time.sleep(1)
    assert completed is not None, "Campaign did not complete in time"
    assert completed["sent"] == 2, f"Expected sent=2 got {completed}"
    assert completed["failed"] == 0


def test_send_empty_audience_returns_400():
    tok = STATE["admin_token"]
    # Create a course with no enrollments
    r = requests.post(f"{BASE_URL}/api/courses", headers=_h(tok),
                      json={"title": "TEST empty course", "description": "x",
                            "modules": [{"title": "M", "hours": 1, "content": "c"}]},
                      timeout=15)
    assert r.status_code in (200, 201)
    empty_cid = r.json()["id"]
    try:
        r = requests.post(f"{BASE_URL}/api/admin/messages/send",
                          headers=_h(tok),
                          json={"subject": "x", "body": "y",
                                "audience": {"type": "course", "course_id": empty_cid}},
                          timeout=15)
        assert r.status_code == 400
    finally:
        db.courses.delete_one({"id": empty_cid})
        db.modules.delete_many({"course_id": empty_cid})
