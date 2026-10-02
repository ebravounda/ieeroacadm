"""Backend API tests for OTEC platform.

Covers: auth OTP, users CRUD, courses/modules, sequential locking, submissions,
AI analysis background, final exam -> diploma, live classes, analytics, settings,
role guards. Uses passwordless OTP by reading code from Mongo directly.

To avoid Resend email rate limiting we only use real OTP for the auth tests and
mint JWTs directly (same JWT_SECRET as backend) for all other logins.
"""
import os
import time
from datetime import datetime, timezone, timedelta

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://learn-progress-ai-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
JWT_SECRET = os.environ.get("JWT_SECRET", "9b8c2d93187f35443f33a88cf2b26ba6d427b87c3ef2498f3a4c40994a660ba9")
mongo = MongoClient(MONGO_URL)[DB_NAME]

ADMIN_EMAIL = "delivered+admin@resend.dev"


# -------- helpers --------
def mint_token(user_id):
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _wait_rate_limit(email):
    rec = mongo.otp_codes.find_one({"email": email})
    if not rec:
        return
    time.sleep(31)


def login_otp(email):
    """Full OTP flow: request-code -> read mongo -> verify-code.

    Retries on 502 (Emergent/Resend email rate limit) with backoff.
    """
    _wait_rate_limit(email)
    for attempt in range(4):
        r = requests.post(f"{API}/auth/request-code", json={"email": email})
        if r.status_code == 502:
            time.sleep(45)
            continue
        if r.status_code == 429:
            time.sleep(31)
            continue
        break
    if r.status_code != 200:
        pytest.skip(f"Upstream email provider unavailable ({r.status_code})")
    time.sleep(0.3)
    rec = mongo.otp_codes.find_one({"email": email})
    assert rec, "OTP record not found"
    r = requests.post(f"{API}/auth/verify-code", json={"email": email, "code": rec["code"]})
    assert r.status_code == 200, f"verify-code failed {r.text}"
    return r.json()["token"]


def login_as(email):
    """Faster login: find user and mint JWT directly (bypasses email)."""
    u = mongo.users.find_one({"email": email.lower(), "active": True})
    assert u, f"user {email} not found"
    return mint_token(u["id"])


def auth_h(token):
    return {"Authorization": f"Bearer {token}"}


def auth_h(token):
    return {"Authorization": f"Bearer {token}"}


def auth_h(token):
    return {"Authorization": f"Bearer {token}"}


def make_student(admin_token, label, course_id=None):
    """Create a student via admin API (no email), optionally enroll. Returns (user, token)."""
    email = f"delivered+{label}{int(time.time()*1000) % 1000000}@resend.dev"
    r = requests.post(f"{API}/users", headers=auth_h(admin_token), json={
        "email": email, "nombre": f"TEST_{label}", "apellidos": "Student",
        "rut": "", "role": "estudiante", "course_id": course_id})
    assert r.status_code == 200, r.text
    u = r.json()
    return u, mint_token(u["id"])


# -------- fixtures --------
@pytest.fixture(scope="session")
def admin_token():
    # Mint directly to avoid email round-trip; auth OTP is tested separately.
    return login_as(ADMIN_EMAIL)


@pytest.fixture(scope="session")
def test_course(admin_token):
    r = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
        "title": "TEST_Curso1", "description": "Curso de pruebas", "code": "T1",
        "hours": 10, "auto_enroll": True, "published": True})
    assert r.status_code == 200, r.text
    return r.json()


# -------- Auth --------
class TestAuth:
    def test_request_code_unknown_email(self):
        r = requests.post(f"{API}/auth/request-code", json={"email": "nosuch_delivered@resend.dev"})
        assert r.status_code == 404

    def test_wrong_code_rejected(self):
        email = "delivered+wrongcode@resend.dev"
        if not mongo.users.find_one({"email": email}):
            mongo.users.insert_one({"id": "test-wrongcode-1", "email": email, "nombre": "TEST_Wrong",
                                    "apellidos": "Code", "rut": "", "role": "estudiante", "active": True,
                                    "created_at": "2026-01-01T00:00:00+00:00", "last_login": None,
                                    "signup_method": "seed"})
        _wait_rate_limit(email)
        for _ in range(4):
            r = requests.post(f"{API}/auth/request-code", json={"email": email})
            if r.status_code in (502, 429):
                time.sleep(45)
                continue
            break
        if r.status_code != 200:
            pytest.skip(f"Upstream email provider unavailable ({r.status_code})")
        time.sleep(0.3)
        r = requests.post(f"{API}/auth/verify-code", json={"email": email, "code": "000000"})
        assert r.status_code == 400

    def test_login_full_flow(self):
        # Real OTP flow against delivered+admin
        tok = login_otp(ADMIN_EMAIL)
        assert isinstance(tok, str) and len(tok) > 10
        r = requests.get(f"{API}/auth/me", headers=auth_h(tok))
        assert r.status_code == 200
        assert r.json()["role"] == "admin"


# -------- User management --------
class TestUsers:
    def test_list_users(self, admin_token):
        r = requests.get(f"{API}/users", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_user_manual(self, admin_token, test_course):
        email = f"delivered+create{int(time.time())}@resend.dev"
        r = requests.post(f"{API}/users", headers=auth_h(admin_token), json={
            "email": email, "nombre": "TEST_Create", "apellidos": "User", "rut": "11.111.111-1",
            "role": "estudiante", "course_id": test_course["id"]})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == email
        # Verify enrollment created
        enr = mongo.enrollments.find_one({"user_id": u["id"], "course_id": test_course["id"]})
        assert enr is not None
        return u

    def test_csv_import(self, admin_token, test_course):
        ts = int(time.time())
        csv_text = (
            "email,nombre,apellidos,rut\n"
            f"delivered+csv1_{ts}@resend.dev,TEST_CSV1,Apel1,22.222.222-2\n"
            f"delivered+csv2_{ts}@resend.dev,TEST_CSV2,Apel2,33.333.333-3\n"
        )
        r = requests.post(f"{API}/users/import", headers=auth_h(admin_token),
                          json={"csv_text": csv_text, "course_id": test_course["id"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created"] == 2
        assert data["errors"] == []

    def test_deactivate_user(self, admin_token):
        email = f"delivered+deact{int(time.time())}@resend.dev"
        r = requests.post(f"{API}/users", headers=auth_h(admin_token), json={
            "email": email, "nombre": "TEST_Deact", "apellidos": "U", "role": "estudiante"})
        uid = r.json()["id"]
        r = requests.put(f"{API}/users/{uid}", headers=auth_h(admin_token), json={"active": False})
        assert r.status_code == 200
        assert r.json()["active"] is False

    def test_self_register_auto_enroll(self, test_course):
        email = f"delivered+selfreg{int(time.time())}@resend.dev"
        for _ in range(4):
            r = requests.post(f"{API}/auth/register", json={
                "email": email, "nombre": "TEST_SelfReg", "apellidos": "Student", "rut": ""})
            if r.status_code in (502, 429):
                time.sleep(45)
                continue
            break
        if r.status_code != 200:
            pytest.skip(f"Upstream email provider unavailable ({r.status_code})")
        u = mongo.users.find_one({"email": email})
        assert u is not None
        enr = mongo.enrollments.find_one({"user_id": u["id"], "course_id": test_course["id"]})
        assert enr is not None, "Self registered user should be auto-enrolled"


# -------- Courses & modules --------
@pytest.fixture(scope="session")
def modules_setup(admin_token, test_course):
    """Create two modules; module1 has quiz, module2 has quiz."""
    cid = test_course["id"]
    # Module 1 with MC quiz
    r = requests.post(f"{API}/courses/{cid}/modules", headers=auth_h(admin_token), json={
        "title": "TEST_Modulo1", "content": "Contenido 1",
        "quiz": {"pass_score": 60, "questions": [
            {"id": "q1", "type": "mc", "text": "2+2?", "options": ["3", "4", "5"], "correct": 1},
            {"id": "q2", "type": "open", "text": "Explica brevemente", "options": [], "correct": None}]}})
    assert r.status_code == 200, r.text
    m1 = r.json()
    # Module 2 with simple MC quiz
    r = requests.post(f"{API}/courses/{cid}/modules", headers=auth_h(admin_token), json={
        "title": "TEST_Modulo2", "content": "Contenido 2",
        "quiz": {"pass_score": 60, "questions": [
            {"id": "q1", "type": "mc", "text": "Cielo?", "options": ["azul", "verde"], "correct": 0}]}})
    assert r.status_code == 200, r.text
    m2 = r.json()
    # Final exam
    r = requests.put(f"{API}/courses/{cid}/final-exam", headers=auth_h(admin_token), json={
        "pass_score": 60,
        "questions": [{"id": "f1", "type": "mc", "text": "Resultado?", "options": ["A", "B"], "correct": 0}]})
    assert r.status_code == 200
    return {"m1": m1, "m2": m2, "course_id": cid}


class TestCoursesModules:
    def test_list_courses(self, admin_token, test_course):
        r = requests.get(f"{API}/courses", headers=auth_h(admin_token))
        assert r.status_code == 200
        titles = [c.get("title", "") for c in r.json()]
        assert test_course["title"] in titles

    def test_module_2_locked_for_student(self, admin_token, modules_setup):
        _, tok = make_student(admin_token, "lock", modules_setup["course_id"])
        # Try to access module 2 without passing module 1
        r = requests.get(f"{API}/modules/{modules_setup['m2']['id']}", headers=auth_h(tok))
        assert r.status_code == 403
        # Module 1 unlocked
        r = requests.get(f"{API}/modules/{modules_setup['m1']['id']}", headers=auth_h(tok))
        assert r.status_code == 200
        # Quiz should not contain correct answers
        q = r.json()["quiz"]["questions"][0]
        assert "correct" not in q

    def test_submit_and_unlock(self, admin_token, modules_setup):
        _, tok = make_student(admin_token, "pass", modules_setup["course_id"])
        # Submit module 1 with correct answers
        r = requests.post(f"{API}/modules/{modules_setup['m1']['id']}/submit",
                          headers=auth_h(tok),
                          json={"answers": {"q1": "1", "q2": "Mi respuesta extensa"},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 60})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["passed"] is True
        assert data["score"] == 100
        # Module 2 should now be accessible
        r = requests.get(f"{API}/modules/{modules_setup['m2']['id']}", headers=auth_h(tok))
        assert r.status_code == 200

    def test_final_exam_locked_until_modules_done(self, admin_token, modules_setup):
        _, tok = make_student(admin_token, "final", modules_setup["course_id"])
        # Final exam locked
        r = requests.get(f"{API}/courses/{modules_setup['course_id']}/final-exam", headers=auth_h(tok))
        assert r.status_code == 403
        # Complete modules
        requests.post(f"{API}/modules/{modules_setup['m1']['id']}/submit", headers=auth_h(tok),
                      json={"answers": {"q1": "1", "q2": "ok"}, "duration_sec": 10,
                            "tab_switches": 0, "paste_events": 0})
        requests.post(f"{API}/modules/{modules_setup['m2']['id']}/submit", headers=auth_h(tok),
                      json={"answers": {"q1": "0"}, "duration_sec": 10,
                            "tab_switches": 0, "paste_events": 0})
        r = requests.get(f"{API}/courses/{modules_setup['course_id']}/final-exam", headers=auth_h(tok))
        assert r.status_code == 200
        # Submit final
        r = requests.post(f"{API}/courses/{modules_setup['course_id']}/final-exam/submit",
                          headers=auth_h(tok),
                          json={"answers": {"f1": "0"}, "duration_sec": 60,
                                "tab_switches": 0, "paste_events": 0})
        assert r.status_code == 200
        res = r.json()
        assert res["passed"] is True
        assert res["diploma_code"]
        # Verify diploma publicly
        pr = requests.get(f"{API}/public/verify/{res['diploma_code']}")
        assert pr.status_code == 200
        assert pr.json()["valid"] is True

    def test_public_verify_invalid(self):
        r = requests.get(f"{API}/public/verify/INVALID999")
        assert r.status_code == 404


# -------- Submissions / AI --------
class TestSubmissions:
    def test_submissions_list_and_ai(self, admin_token):
        r = requests.get(f"{API}/submissions", headers=auth_h(admin_token))
        assert r.status_code == 200
        subs = r.json()
        assert isinstance(subs, list)
        # Wait a bit for AI analysis to complete on recent ones
        time.sleep(15)
        r = requests.get(f"{API}/submissions", headers=auth_h(admin_token))
        subs = r.json()
        completed = [s for s in subs if s["ai_status"] == "completado"]
        # At least one submission should have completed AI analysis
        assert len(completed) >= 1, f"No completed AI analyses: statuses={[s['ai_status'] for s in subs[:10]]}"
        s = completed[0]
        assert "percentage" in s["ai_analysis"]
        # Reanalyze endpoint
        r = requests.post(f"{API}/submissions/{s['id']}/analyze", headers=auth_h(admin_token))
        assert r.status_code == 200


# -------- Live classes --------
class TestLiveClasses:
    def test_live_class_statuses(self, admin_token, test_course):
        from datetime import datetime, timezone, timedelta
        # En vivo: start 5 min ago, end 60 min from now
        now = datetime.now(timezone.utc)
        live = {
            "course_id": test_course["id"], "title": "TEST_LiveNow", "platform": "meet",
            "url": "https://meet.google.com/test-abc-xyz",
            "start_at": (now - timedelta(minutes=5)).isoformat(),
            "end_at": (now + timedelta(hours=1)).isoformat()}
        r = requests.post(f"{API}/live-classes", headers=auth_h(admin_token), json=live)
        assert r.status_code == 200
        live_id = r.json()["id"]
        # Programada
        prog = {**live, "title": "TEST_LiveFuture",
                "start_at": (now + timedelta(days=1)).isoformat(),
                "end_at": (now + timedelta(days=1, hours=1)).isoformat()}
        r = requests.post(f"{API}/live-classes", headers=auth_h(admin_token), json=prog)
        prog_id = r.json()["id"]

        # Student view
        _, tok = make_student(admin_token, "liveview", test_course["id"])
        r = requests.get(f"{API}/live-classes", headers=auth_h(tok))
        assert r.status_code == 200
        rows = {c["id"]: c for c in r.json()}
        assert rows[live_id]["status"] == "en_vivo"
        assert "url" in rows[live_id]
        assert rows[prog_id]["status"] == "programada"
        assert "url" not in rows[prog_id], "Future class should not expose URL to students"

        # Join live class
        r = requests.post(f"{API}/live-classes/{live_id}/join", headers=auth_h(tok))
        assert r.status_code == 200
        assert r.json()["url"].startswith("https://")

        # Student can't join future class
        r = requests.post(f"{API}/live-classes/{prog_id}/join", headers=auth_h(tok))
        assert r.status_code == 400

    def test_live_class_rejects_non_https(self, admin_token, test_course):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        r = requests.post(f"{API}/live-classes", headers=auth_h(admin_token), json={
            "course_id": test_course["id"], "title": "TEST_Bad", "platform": "meet",
            "url": "http://insecure.example.com",
            "start_at": now.isoformat(), "end_at": (now + timedelta(hours=1)).isoformat()})
        assert r.status_code == 400


# -------- Activity / heartbeat --------
class TestActivity:
    def test_heartbeat(self, admin_token):
        r = requests.post(f"{API}/activity/heartbeat", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert r.json()["ok"] is True


# -------- Analytics --------
class TestAnalytics:
    def test_overview(self, admin_token):
        r = requests.get(f"{API}/analytics/overview", headers=auth_h(admin_token))
        assert r.status_code == 200
        data = r.json()
        for k in ("students", "courses", "enrollments", "diplomas", "daily"):
            assert k in data

    def test_students_table(self, admin_token):
        r = requests.get(f"{API}/analytics/students", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# -------- Settings --------
class TestSettings:
    def test_get_settings(self, admin_token):
        r = requests.get(f"{API}/settings", headers=auth_h(admin_token))
        assert r.status_code == 200

    def test_update_names(self, admin_token):
        r = requests.put(f"{API}/settings", headers=auth_h(admin_token), json={
            "otec_name": "TEST_OTEC", "rector_name": "TEST_Rector Juan",
            "vicerrector_name": "TEST_Vice Maria"})
        assert r.status_code == 200
        s = r.json()
        assert s["rector_name"] == "TEST_Rector Juan"

    def test_rejects_non_png_signature(self, admin_token):
        r = requests.put(f"{API}/settings", headers=auth_h(admin_token), json={
            "rector_signature": "data:image/jpeg;base64,AAAA"})
        assert r.status_code == 400


# -------- Role guards --------
class TestRoleGuards:
    @pytest.fixture(scope="class")
    def student_token(self, admin_token):
        _, tok = make_student(admin_token, "guard")
        return tok

    def test_student_cannot_list_users(self, student_token):
        r = requests.get(f"{API}/users", headers=auth_h(student_token))
        assert r.status_code == 403

    def test_student_cannot_analytics(self, student_token):
        r = requests.get(f"{API}/analytics/overview", headers=auth_h(student_token))
        assert r.status_code == 403

    def test_student_cannot_write_settings(self, student_token):
        r = requests.put(f"{API}/settings", headers=auth_h(student_token), json={"otec_name": "X"})
        assert r.status_code == 403
