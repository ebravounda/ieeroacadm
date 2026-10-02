"""Iteration 15: Módulo 0 Bienvenida auto-created in every course.

Covers:
- POST /api/courses auto-creates a module with welcome=true, order=0,
  title 'Bienvenida al curso', 1 section 'Bienvenida al alumno/a',
  1 video material with url '/bienvenida.mp4'
- On startup, ensure_welcome runs for every existing course without a welcome module;
  enrollments that already had completed_modules or final_passed get the welcome module
  added to completed_modules
- POST /api/courses/{id}/modules continues numbering from max(order)+1
- POST /api/courses/{id}/import-modules continues numbering from max(order)+1
- DELETE /api/modules/{welcome_id} returns 400
- Student module 1 locked until welcome module completed; welcome module has no quiz
  and can be completed via POST /modules/{id}/complete after task marked done
- /bienvenida.mp4 served 200 video/mp4
"""
import os
import time
import subprocess
from datetime import datetime, timezone, timedelta

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
JWT_SECRET = os.environ["JWT_SECRET"]
mongo = MongoClient(MONGO_URL)[DB_NAME]

ADMIN_EMAIL = "info@iberoacademy.cl"


def mint(uid):
    return pyjwt.encode({"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(days=1), "type": "access"},
                        JWT_SECRET, algorithm="HS256")


def h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    u = mongo.users.find_one({"email": ADMIN_EMAIL})
    assert u
    return mint(u["id"])


# ---------- cleanup registry ----------
CREATED = {"course_ids": [], "user_ids": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for cid in CREATED["course_ids"]:
        mongo.modules.delete_many({"course_id": cid})
        mongo.enrollments.delete_many({"course_id": cid})
        mongo.quiz_draws.delete_many({"course_id": cid})
        mongo.submissions.delete_many({"course_id": cid})
        mongo.courses.delete_one({"id": cid})
    for uid in CREATED["user_ids"]:
        mongo.enrollments.delete_many({"user_id": uid})
        mongo.module_sessions.delete_many({"user_id": uid})
        mongo.users.delete_one({"id": uid})


def _mk_course(admin_token, title_suffix=""):
    r = requests.post(f"{API}/courses", headers=h(admin_token), json={
        "title": f"TEST_Welcome{title_suffix}", "description": "", "code": f"TW{title_suffix}",
        "hours": 1, "auto_enroll": False, "published": True})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    CREATED["course_ids"].append(cid)
    return cid


def _mk_student(admin_token, label, course_id=None):
    email = f"delivered+TEST_W_{label}_{int(time.time()*1000)%1000000}@resend.dev"
    body = {"email": email, "nombre": f"TEST_W_{label}", "apellidos": "S", "role": "estudiante"}
    if course_id:
        body["course_id"] = course_id
    r = requests.post(f"{API}/users", headers=h(admin_token), json=body)
    assert r.status_code == 200, r.text
    u = r.json()
    CREATED["user_ids"].append(u["id"])
    return u, mint(u["id"])


# ---------- Tests ----------
class TestWelcomeOnCreate:
    def test_course_creation_adds_welcome_module(self, admin_token):
        cid = _mk_course(admin_token, "_create")
        mods = list(mongo.modules.find({"course_id": cid}).sort("order", 1))
        assert len(mods) == 1
        m = mods[0]
        assert m["welcome"] is True
        assert m["order"] == 0
        assert m["title"] == "Bienvenida al curso"
        assert len(m["sections"]) == 1
        assert m["sections"][0]["title"] == "Bienvenida al alumno/a"
        assert len(m["materials"]) == 1
        mat = m["materials"][0]
        assert mat["type"] == "video"
        assert mat["url"] == "/bienvenida.mp4"

    def test_welcome_video_served(self):
        r = requests.get(f"{BASE_URL}/bienvenida.mp4", stream=True, timeout=15)
        assert r.status_code == 200
        assert "video/mp4" in r.headers.get("content-type", "")


class TestNumbering:
    def test_added_module_order_is_1(self, admin_token):
        cid = _mk_course(admin_token, "_num")
        r = requests.post(f"{API}/courses/{cid}/modules", headers=h(admin_token), json={
            "title": "TEST_M1", "min_minutes": 0, "materials": [], "sections": [],
            "quiz": {"questions": [], "pass_score": 75, "draw_count": 10}})
        assert r.status_code == 200
        assert r.json()["order"] == 1
        r2 = requests.post(f"{API}/courses/{cid}/modules", headers=h(admin_token), json={
            "title": "TEST_M2", "min_minutes": 0, "materials": [], "sections": [],
            "quiz": {"questions": [], "pass_score": 75, "draw_count": 10}})
        assert r2.json()["order"] == 2

    def test_import_modules_continues_numbering(self, admin_token):
        cid = _mk_course(admin_token, "_imp")
        text = ("MÓDULO 1: Introducción\n"
                "Objetivo: aprender\n"
                "Lección 1. Tema uno\n"
                "Contenido A\n"
                "MÓDULO 2: Avanzado\n"
                "Objetivo: profundizar\n"
                "Lección 1. Tema dos\n"
                "Contenido B\n")
        r = requests.post(f"{API}/courses/{cid}/import-modules", headers=h(admin_token),
                          json={"text": text, "dry_run": False})
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 2
        mods = list(mongo.modules.find({"course_id": cid}).sort("order", 1))
        orders = [m["order"] for m in mods]
        assert orders == [0, 1, 2]
        assert mods[0]["welcome"] is True


class TestDeleteWelcome:
    def test_delete_welcome_forbidden(self, admin_token):
        cid = _mk_course(admin_token, "_del")
        welcome = mongo.modules.find_one({"course_id": cid, "welcome": True})
        r = requests.delete(f"{API}/modules/{welcome['id']}", headers=h(admin_token))
        assert r.status_code == 400


class TestEnsureWelcomeOnStartup:
    def test_startup_backfills_welcome_and_enrollments(self, admin_token):
        # Insert a course directly with NO welcome module, and enrollments with
        # non-empty completed_modules / final_passed to simulate in-progress students.
        import uuid
        cid = "TEST_bf_" + uuid.uuid4().hex[:8]
        mongo.courses.insert_one({
            "id": cid, "title": "TEST_Backfill", "description": "", "code": "TBF",
            "hours": 0, "auto_enroll": False, "published": True, "price": 0,
            "summary": "", "modality": "", "image_file_id": "", "show_on_landing": False,
            "teacher_id": "x", "created_at": datetime.now(timezone.utc).isoformat(),
            "final_exam": {"questions": [], "pass_score": 75, "draw_count": 10}})
        CREATED["course_ids"].append(cid)
        # Add a real module (not welcome) to the course
        other_mid = "TEST_oth_" + uuid.uuid4().hex[:6]
        mongo.modules.insert_one({"id": other_mid, "course_id": cid, "order": 1,
                                  "title": "TEST_Other", "description": "", "content": "",
                                  "video_url": "", "min_minutes": 0, "materials": [],
                                  "sections": [], "quiz": {"questions": [], "pass_score": 75, "draw_count": 10}})
        # Enrollment A: completed_modules non-empty -> should receive welcome on backfill
        u_a, _ = _mk_student(admin_token, "bfA")
        e_a_id = "TEST_eA_" + uuid.uuid4().hex[:6]
        mongo.enrollments.insert_one({"id": e_a_id, "user_id": u_a["id"], "course_id": cid,
                                      "method": "manual", "enrolled_at": datetime.now(timezone.utc).isoformat(),
                                      "completed_modules": [other_mid], "final_passed": False,
                                      "completed_at": None})
        # Enrollment B: brand new (empty completed_modules, not final_passed) -> should NOT be auto-added
        u_b, _ = _mk_student(admin_token, "bfB")
        e_b_id = "TEST_eB_" + uuid.uuid4().hex[:6]
        mongo.enrollments.insert_one({"id": e_b_id, "user_id": u_b["id"], "course_id": cid,
                                      "method": "manual", "enrolled_at": datetime.now(timezone.utc).isoformat(),
                                      "completed_modules": [], "final_passed": False,
                                      "completed_at": None})
        # Enrollment C: final_passed=True (even if completed_modules empty)
        u_c, _ = _mk_student(admin_token, "bfC")
        e_c_id = "TEST_eC_" + uuid.uuid4().hex[:6]
        mongo.enrollments.insert_one({"id": e_c_id, "user_id": u_c["id"], "course_id": cid,
                                      "method": "manual", "enrolled_at": datetime.now(timezone.utc).isoformat(),
                                      "completed_modules": [], "final_passed": True,
                                      "completed_at": datetime.now(timezone.utc).isoformat()})
        # Sanity: no welcome yet
        assert mongo.modules.find_one({"course_id": cid, "welcome": True}) is None

        # Restart backend to trigger startup ensure_welcome
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
        # Wait for backend to come back
        for _ in range(60):
            try:
                if requests.get(f"{API}/courses", timeout=3).status_code in (200, 401, 403):
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(2)

        welcome = mongo.modules.find_one({"course_id": cid, "welcome": True})
        assert welcome is not None, "Welcome module not backfilled on startup"
        assert welcome["order"] == 0
        wid = welcome["id"]

        e_a = mongo.enrollments.find_one({"id": e_a_id})
        e_b = mongo.enrollments.find_one({"id": e_b_id})
        e_c = mongo.enrollments.find_one({"id": e_c_id})
        assert wid in e_a["completed_modules"], "In-progress enrollment should get welcome added"
        assert wid not in e_b["completed_modules"], "Fresh enrollment should NOT be auto-marked"
        assert wid in e_c["completed_modules"], "final_passed enrollment should get welcome added"


class TestStudentFlow:
    def test_module1_locked_until_welcome_done(self, admin_token):
        cid = _mk_course(admin_token, "_flow")
        # add module 1 (no quiz, no min_minutes)
        r = requests.post(f"{API}/courses/{cid}/modules", headers=h(admin_token), json={
            "title": "TEST_M1", "min_minutes": 0, "materials": [], "sections": [],
            "quiz": {"questions": [], "pass_score": 75, "draw_count": 10}})
        m1_id = r.json()["id"]
        _, tok = _mk_student(admin_token, "flow", cid)

        # Welcome module id
        welcome = mongo.modules.find_one({"course_id": cid, "welcome": True})
        wid = welcome["id"]
        mat_id = welcome["materials"][0]["id"]

        # Module 1 should be locked
        r_m1 = requests.get(f"{API}/modules/{m1_id}", headers=h(tok))
        assert r_m1.status_code == 403

        # Course view shows unlocked for welcome only
        r_c = requests.get(f"{API}/courses/{cid}", headers=h(tok))
        assert r_c.status_code == 200
        mods = r_c.json()["modules"]
        assert mods[0]["id"] == wid and mods[0]["unlocked"] is True and mods[0]["completed"] is False
        assert mods[1]["id"] == m1_id and mods[1]["unlocked"] is False

        # Open welcome module (allowed)
        r_w = requests.get(f"{API}/modules/{wid}", headers=h(tok))
        assert r_w.status_code == 200
        assert r_w.json()["order"] == 0

        # Mark video task complete
        r_t = requests.post(f"{API}/modules/{wid}/tasks/{mat_id}/complete", headers=h(tok))
        assert r_t.status_code == 200

        # Finalize welcome module (no quiz, no min_minutes)
        r_fin = requests.post(f"{API}/modules/{wid}/complete", headers=h(tok))
        assert r_fin.status_code == 200, r_fin.text

        # Module 1 should now be unlocked
        r_m1b = requests.get(f"{API}/modules/{m1_id}", headers=h(tok))
        assert r_m1b.status_code == 200
