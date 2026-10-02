"""Iteration 4: OTEC course report + attendance certificates."""
import os
import time
import requests
import pytest
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://learn-progress-ai-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
JWT_SECRET = os.environ.get("JWT_SECRET", "9b8c2d93187f35443f33a88cf2b26ba6d427b87c3ef2498f3a4c40994a660ba9")
mongo = MongoClient(MONGO_URL)[DB_NAME]
ADMIN_EMAIL = "delivered+admin@resend.dev"


def mint(uid, exp_minutes=60 * 24):
    return pyjwt.encode(
        {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes), "type": "access"},
        JWT_SECRET, algorithm="HS256")


def auth_h(t):
    return {"Authorization": f"Bearer {t}"}


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


@pytest.fixture(scope="module")
def admin():
    u = mongo.users.find_one({"email": ADMIN_EMAIL.lower(), "active": True})
    if not u:
        import uuid
        uid = f"test-admin-i4-{uuid.uuid4().hex[:8]}"
        doc = {"id": uid, "email": ADMIN_EMAIL.lower(), "nombre": "TEST", "apellidos": "Admin",
               "rut": "", "role": "admin", "active": True,
               "created_at": datetime.now(timezone.utc).isoformat()}
        mongo.users.insert_one(doc)
        u = mongo.users.find_one({"id": uid}, {"_id": 0})
    return {"user": u, "token": mint(u["id"])}


@pytest.fixture(scope="module")
def seed(admin):
    """Create course + module + 2 students + 2 live classes (one finished, one future).
    Student A attended finished class; Student B did not."""
    import uuid
    tok = admin["token"]
    # Course
    r = requests.post(f"{API}/courses", headers=auth_h(tok), json={
        "title": "TEST_i4_course", "description": "OTEC report test",
        "code": "I4R", "hours": 10, "auto_enroll": False, "published": True})
    assert r.status_code == 200, r.text
    c = r.json()
    # Module (small quiz so modules_total > 0)
    r = requests.post(f"{API}/courses/{c['id']}/modules", headers=auth_h(tok), json={
        "title": "TEST_i4_mod", "content": "",
        "quiz": {"pass_score": 75, "questions": [
            {"id": "q1", "type": "single", "text": "2+2?", "options": ["3", "4"], "correct": "4"}]}})
    assert r.status_code == 200, r.text
    m = r.json()

    # 2 students via /api/users (which auto-enrolls when course_id passed)
    ts = int(time.time() * 1000) % 1000000
    students = []
    for i, nm in enumerate([("TEST_i4A", "Alpha"), ("TEST_i4B", "Beta")]):
        email = f"delivered+i4stu{ts}{i}@resend.dev"
        r = requests.post(f"{API}/users", headers=auth_h(tok), json={
            "email": email, "nombre": nm[0], "apellidos": nm[1],
            "rut": f"11111111-{i}", "role": "estudiante", "course_id": c["id"]})
        assert r.status_code == 200, r.text
        s = r.json()
        students.append({"user": s, "token": mint(s["id"])})

    # 2 live classes: finished (2h ago -> 1h ago), future (in 1h -> 2h)
    now = datetime.now(timezone.utc)
    finished = {"id": f"test-cls-fin-{ts}", "course_id": c["id"],
                "title": "TEST_i4_finished", "platform": "teams",
                "url": "https://teams.example.com/x",
                "start_at": iso(now - timedelta(hours=2)),
                "end_at": iso(now - timedelta(hours=1)),
                "created_at": iso(now - timedelta(days=1))}
    future = {"id": f"test-cls-fut-{ts}", "course_id": c["id"],
              "title": "TEST_i4_future", "platform": "meet",
              "url": "https://meet.example.com/y",
              "start_at": iso(now + timedelta(hours=1)),
              "end_at": iso(now + timedelta(hours=2)),
              "created_at": iso(now - timedelta(days=1))}
    mongo.live_classes.insert_many([finished, future])

    # Student A attended finished class
    mongo.live_attendance.insert_one({
        "id": str(uuid.uuid4()),
        "class_id": finished["id"], "user_id": students[0]["user"]["id"],
        "joined_at": iso(now - timedelta(hours=1, minutes=50))})

    return {"course": c, "module": m, "students": students,
            "finished": finished, "future": future}


# ---------------- OTEC Course Report ----------------
class TestCourseReport:
    def test_report_requires_staff(self, seed):
        stu_tok = seed["students"][0]["token"]
        r = requests.get(f"{API}/courses/{seed['course']['id']}/report", headers=auth_h(stu_tok))
        assert r.status_code == 403

    def test_report_unauth(self, seed):
        r = requests.get(f"{API}/courses/{seed['course']['id']}/report")
        assert r.status_code == 401

    def test_report_shape_and_rows(self, admin, seed):
        r = requests.get(f"{API}/courses/{seed['course']['id']}/report", headers=auth_h(admin["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["course"]["id"] == seed["course"]["id"]
        assert d["course"]["title"] == "TEST_i4_course"
        # summary
        assert d["summary"]["students"] >= 2
        assert d["summary"]["live_classes"] == 2
        assert d["summary"]["approved"] == 0  # nobody passed yet
        # rows
        emails = {s["user"]["email"].lower() for s in seed["students"]}
        rows = [row for row in d["rows"] if row["email"].lower() in emails]
        assert len(rows) == 2
        a = next(row for row in rows if row["email"] == seed["students"][0]["user"]["email"].lower())
        b = next(row for row in rows if row["email"] == seed["students"][1]["user"]["email"].lower())
        # Student A attended 1/2 live classes
        assert a["live_total"] == 2
        assert a["live_attended"] == 1
        assert a["modules_total"] == 1
        assert a["status"] == "En curso"
        # Student B attended 0
        assert b["live_attended"] == 0
        # overall_nota exists as key (may be None)
        assert "overall_nota" in a

    def test_report_404(self, admin):
        r = requests.get(f"{API}/courses/does-not-exist/report", headers=auth_h(admin["token"]))
        assert r.status_code == 404


# ---------------- Attendance certificate ----------------
class TestAttendanceCertificate:
    def test_cert_404_if_not_attended(self, seed):
        tok = seed["students"][1]["token"]  # didn't attend
        r = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate", headers=auth_h(tok))
        assert r.status_code == 404

    def test_cert_400_if_not_finished(self, seed):
        # Attend future class, then try to issue
        tok = seed["students"][0]["token"]
        mongo.live_attendance.insert_one({
            "id": "test-att-future", "class_id": seed["future"]["id"],
            "user_id": seed["students"][0]["user"]["id"],
            "joined_at": datetime.now(timezone.utc).isoformat()})
        try:
            r = requests.post(f"{API}/live-classes/{seed['future']['id']}/certificate", headers=auth_h(tok))
            assert r.status_code == 400
        finally:
            mongo.live_attendance.delete_one({"id": "test-att-future"})

    def test_cert_create_and_idempotent(self, seed):
        tok = seed["students"][0]["token"]
        r1 = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate", headers=auth_h(tok))
        assert r1.status_code == 200, r1.text
        code1 = r1.json()["code"]
        assert code1.startswith("A") and len(code1) >= 6
        r2 = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate", headers=auth_h(tok))
        assert r2.status_code == 200
        assert r2.json()["code"] == code1

    def test_get_certificate_owner(self, seed):
        tok = seed["students"][0]["token"]
        code = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate",
                             headers=auth_h(tok)).json()["code"]
        r = requests.get(f"{API}/attendance-certificates/{code}", headers=auth_h(tok))
        assert r.status_code == 200
        d = r.json()
        assert d["code"] == code
        assert "Alpha" in d["student_name"]
        assert d["class_title"] == "TEST_i4_finished"
        assert d["platform"] == "Microsoft Teams"
        assert "otec_name" in d
        assert d["user_id"] == seed["students"][0]["user"]["id"]

    def test_get_certificate_other_student_forbidden(self, seed):
        tok = seed["students"][0]["token"]
        code = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate",
                             headers=auth_h(tok)).json()["code"]
        other = seed["students"][1]["token"]
        r = requests.get(f"{API}/attendance-certificates/{code}", headers=auth_h(other))
        assert r.status_code == 403

    def test_get_certificate_staff_ok(self, seed, admin):
        tok = seed["students"][0]["token"]
        code = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate",
                             headers=auth_h(tok)).json()["code"]
        r = requests.get(f"{API}/attendance-certificates/{code}", headers=auth_h(admin["token"]))
        assert r.status_code == 200

    def test_public_verify_no_auth_no_leak(self, seed):
        tok = seed["students"][0]["token"]
        code = requests.post(f"{API}/live-classes/{seed['finished']['id']}/certificate",
                             headers=auth_h(tok)).json()["code"]
        r = requests.get(f"{API}/public/verify-attendance/{code}")
        assert r.status_code == 200
        d = r.json()
        assert d["valid"] is True
        assert "user_id" not in d
        assert "student_name" in d
        assert d["class_title"] == "TEST_i4_finished"

    def test_public_verify_invalid(self):
        r = requests.get(f"{API}/public/verify-attendance/NOPE123")
        assert r.status_code == 404


# ---------------- Regression: live classes attended flag ----------------
class TestLiveClassesRegression:
    def test_live_classes_attended_flag(self, seed):
        tok = seed["students"][0]["token"]
        r = requests.get(f"{API}/live-classes", headers=auth_h(tok))
        assert r.status_code == 200
        rows = {c["id"]: c for c in r.json()}
        assert seed["finished"]["id"] in rows
        assert rows[seed["finished"]["id"]]["status"] == "finalizada"
        assert rows[seed["finished"]["id"]].get("attended") is True
        assert rows[seed["future"]["id"]]["status"] == "programada"
        assert rows[seed["future"]["id"]].get("attended") is False
