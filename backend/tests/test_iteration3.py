"""Iteration 3: Office inline viewer + grade email notification tests."""
import io
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


def mint(uid, typ="access", exp_minutes=60 * 24):
    return pyjwt.encode(
        {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(minutes=exp_minutes), "type": typ},
        JWT_SECRET, algorithm="HS256")


def auth_h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    u = mongo.users.find_one({"email": ADMIN_EMAIL.lower(), "active": True})
    assert u, "admin missing"
    return mint(u["id"])


@pytest.fixture(scope="module")
def pptx_file(admin_token):
    # Minimal fake .pptx; viewer-url logic only checks extension
    files = {"file": ("TEST_i3_slides.pptx", io.BytesIO(b"fake pptx bytes"),
                      "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
    r = requests.post(f"{API}/files", headers=auth_h(admin_token), files=files)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def pdf_file(admin_token):
    files = {"file": ("TEST_i3.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    r = requests.post(f"{API}/files", headers=auth_h(admin_token), files=files)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Viewer-URL + Public File ----------
class TestOfficeViewer:
    def test_viewer_url_shape(self, admin_token, pptx_file):
        r = requests.get(f"{API}/files/{pptx_file['id']}/viewer-url", headers=auth_h(admin_token))
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert "/api/public/files/" in url
        assert url.endswith(".pptx")
        assert url.startswith("https://")

    def test_viewer_url_requires_auth(self, pptx_file):
        r = requests.get(f"{API}/files/{pptx_file['id']}/viewer-url")
        assert r.status_code == 401

    def test_viewer_url_404_for_non_office(self, admin_token, pdf_file):
        r = requests.get(f"{API}/files/{pdf_file['id']}/viewer-url", headers=auth_h(admin_token))
        assert r.status_code == 404

    def test_public_file_returns_bytes_without_auth(self, admin_token, pptx_file):
        r = requests.get(f"{API}/files/{pptx_file['id']}/viewer-url", headers=auth_h(admin_token))
        public_url = r.json()["url"]
        # Fetch public URL with no auth
        r2 = requests.get(public_url)
        assert r2.status_code == 200
        assert r2.content == b"fake pptx bytes"

    def test_public_file_invalid_token_403(self):
        r = requests.get(f"{API}/public/files/not-a-real-token/file.pptx")
        assert r.status_code == 403

    def test_file_token_cannot_be_used_as_bearer(self, admin_token, pptx_file):
        # Mint a file-type token for the file id and try to use it as access bearer
        file_tok = mint(pptx_file["id"], typ="file", exp_minutes=60)
        r = requests.get(f"{API}/auth/me", headers=auth_h(file_tok))
        assert r.status_code == 401

    def test_access_token_cannot_decode_as_file(self, admin_token):
        # Access token used as public file token path -> should be 403
        r = requests.get(f"{API}/public/files/{admin_token}/file.pptx")
        assert r.status_code == 403


# ---------- Grade email notification ----------
def _login_as(email):
    u = mongo.users.find_one({"email": email.lower(), "active": True})
    assert u
    return u, mint(u["id"])


class TestGradeEmail:
    @pytest.fixture(scope="class")
    def open_setup(self, admin_token):
        # Create course + module with open question, student submits -> en_revision
        r = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
            "title": "TEST_i3_open", "description": "", "code": "I3O",
            "hours": 1, "auto_enroll": False, "published": True})
        c = r.json()
        r = requests.post(f"{API}/courses/{c['id']}/modules", headers=auth_h(admin_token), json={
            "title": "TEST_i3_open_mod", "content": "",
            "quiz": {"pass_score": 75, "questions": [
                {"id": "o1", "type": "open", "text": "Explica", "options": []}]}})
        m = r.json()

        # Create student
        email = f"delivered+i3stu{int(time.time()*1000) % 1000000}@resend.dev"
        r = requests.post(f"{API}/users", headers=auth_h(admin_token), json={
            "email": email, "nombre": "TEST_i3stu", "apellidos": "Student",
            "role": "estudiante", "course_id": c["id"]})
        stu = r.json()
        stu_tok = mint(stu["id"])

        # Student submits open-question
        r = requests.post(f"{API}/modules/{m['id']}/submit", headers=auth_h(stu_tok),
                          json={"answers": {"o1": "ensayo sobre tema"},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 60})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "en_revision"

        subs = requests.get(f"{API}/submissions", headers=auth_h(admin_token)).json()
        sub = next(s for s in subs if s["module_id"] == m["id"] and s["user_id"] == stu["id"])
        return {"course": c, "module": m, "student": stu, "sub": sub}

    def test_grade_returns_graded_sub_and_triggers_email(self, admin_token, open_setup):
        # Record current size of backend err log
        log_path = "/var/log/supervisor/backend.err.log"
        before_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0

        r = requests.post(f"{API}/submissions/{open_setup['sub']['id']}/grade",
                          headers=auth_h(admin_token),
                          json={"grades": {"o1": 85}, "feedback": "Buen trabajo"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "calificada"
        assert d["score"] == 85
        assert d["nota"] is not None
        assert d["passed"] is True

        # Allow background email task to run
        time.sleep(4)

        # Check err log: must not contain "Grade email failed" since this grade
        if os.path.exists(log_path):
            with open(log_path, "rb") as f:
                f.seek(before_size)
                new_logs = f.read().decode("utf-8", errors="ignore")
            assert "Grade email failed" not in new_logs, f"Found grade email failure: {new_logs[-500:]}"
