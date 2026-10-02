"""Iteration 5: IberoAcademy certificate approval flow (diplomas).

Covers issue_diploma on final-exam pass, admin approve/reject, PDF generation (pymupdf),
QR + approval code, public verify, settings/certificate-preview with custom template.
"""
import io
import os
import re
import time
import uuid
import requests
import pytest
import jwt as pyjwt
import pymupdf
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
mongo = MongoClient(MONGO_URL)[DB_NAME]
ADMIN_EMAIL = "delivered+admin@resend.dev"
REAL_ADMIN_EMAIL = "ed0.2580@gmail.com"
CODE_RE = re.compile(r"^IBA-[A-Z2-9]{4}-[A-Z2-9]{4}$")


def mint(uid, minutes=60 * 24):
    return pyjwt.encode(
        {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes), "type": "access"},
        JWT_SECRET, algorithm="HS256")


def auth_h(t):
    return {"Authorization": f"Bearer {t}"}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module", autouse=True)
def deactivate_real_admin():
    """Mandatory: avoid sending certificate request emails to the real owner."""
    before = mongo.users.find_one({"email": REAL_ADMIN_EMAIL})
    if before and before.get("active"):
        mongo.users.update_one({"email": REAL_ADMIN_EMAIL}, {"$set": {"active": False}})
        yield
        mongo.users.update_one({"email": REAL_ADMIN_EMAIL}, {"$set": {"active": True}})
    else:
        yield


@pytest.fixture(scope="module")
def admin():
    u = mongo.users.find_one({"email": ADMIN_EMAIL.lower(), "active": True})
    if not u:
        uid = f"test-admin-i5-{uuid.uuid4().hex[:8]}"
        doc = {"id": uid, "email": ADMIN_EMAIL.lower(), "nombre": "TEST_Admin", "apellidos": "QA",
               "rut": "", "role": "admin", "active": True,
               "created_at": datetime.now(timezone.utc).isoformat()}
        mongo.users.insert_one(doc)
        u = mongo.users.find_one({"id": uid})
    return {"user": {k: v for k, v in u.items() if k != "_id"}, "token": mint(u["id"])}


@pytest.fixture(scope="module")
def settings_snapshot():
    """Snapshot settings and restore cert_template/cert_layout at the end."""
    before = mongo.settings.find_one({"id": "global"}) or {}
    yield before
    mongo.settings.update_one({"id": "global"},
                              {"$set": {"cert_template": before.get("cert_template", {}),
                                        "cert_layout": before.get("cert_layout", {})}},
                              upsert=True)


@pytest.fixture(scope="module")
def seed(admin):
    """Create course with final_exam, module (no quiz, no materials), 2 students enrolled."""
    tok = admin["token"]
    ts = int(time.time() * 1000) % 1000000

    # Course
    r = requests.post(f"{API}/courses", headers=auth_h(tok), json={
        "title": "TEST_i5_cert_course", "description": "Cert flow test",
        "code": f"I5C{ts}", "hours": 10, "auto_enroll": False, "published": True})
    assert r.status_code == 200, r.text
    c = r.json()

    # Module WITHOUT quiz, WITHOUT materials (so /complete works directly)
    r = requests.post(f"{API}/courses/{c['id']}/modules", headers=auth_h(tok), json={
        "title": "TEST_i5_mod", "content": "x", "quiz": {"pass_score": 75, "questions": []},
        "materials": [], "min_minutes": 0})
    assert r.status_code == 200, r.text
    m = r.json()

    # Final exam: 1 single-choice question
    r = requests.put(f"{API}/courses/{c['id']}/final-exam", headers=auth_h(tok), json={
        "pass_score": 60,
        "questions": [{"id": "fq1", "type": "single", "text": "2+2?", "options": ["3", "4"], "correct": "4"}]})
    assert r.status_code == 200, r.text

    # 2 students (auto-enrolled via course_id)
    students = []
    for i, (nm, ap) in enumerate([("TEST_i5A", "Owner"), ("TEST_i5B", "Other")]):
        email = f"delivered+i5stu{ts}{i}@resend.dev"
        r = requests.post(f"{API}/users", headers=auth_h(tok), json={
            "email": email, "nombre": nm, "apellidos": ap,
            "rut": f"22222222-{i}", "role": "estudiante", "course_id": c["id"]})
        assert r.status_code == 200, r.text
        s = r.json()
        students.append({"user": s, "token": mint(s["id"])})

    return {"course": c, "module": m, "students": students}


@pytest.fixture(scope="module")
def diploma_pending(seed):
    """Student A passes final exam -> diploma status pendiente, returns diploma_code."""
    stu = seed["students"][0]
    # 1) complete the module (no quiz, no materials -> OK)
    r = requests.post(f"{API}/modules/{seed['module']['id']}/complete", headers=auth_h(stu["token"]))
    assert r.status_code == 200, r.text
    # 2) submit final exam with correct answer
    r = requests.post(f"{API}/courses/{seed['course']['id']}/final-exam/submit",
                      headers=auth_h(stu["token"]),
                      json={"answers": {"fq1": "4"}, "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["passed"] is True
    assert body["status"] == "calificada"
    assert body["diploma_code"] and CODE_RE.match(body["diploma_code"]), body
    # Verify DB
    d = mongo.diplomas.find_one({"code": body["diploma_code"]})
    assert d and d["status"] == "pendiente"
    assert d["user_id"] == stu["user"]["id"]
    return {"code": body["diploma_code"], "id": d["id"], "student": stu, "other": seed["students"][1]}


# ---------------- Tests ----------------
class TestIssueDiploma:
    def test_diploma_created_pending(self, diploma_pending):
        assert diploma_pending["code"]
        assert CODE_RE.match(diploma_pending["code"])

    def test_public_verify_404_while_pending(self, diploma_pending):
        r = requests.get(f"{API}/public/verify/{diploma_pending['code']}")
        assert r.status_code == 404

    def test_public_pdf_404_while_pending(self, diploma_pending):
        r = requests.get(f"{API}/public/diplomas/{diploma_pending['code']}/pdf")
        assert r.status_code == 404

    def test_owner_pdf_404_while_pending(self, diploma_pending):
        tok = diploma_pending["student"]["token"]
        r = requests.get(f"{API}/diplomas/{diploma_pending['code']}/pdf", headers=auth_h(tok))
        assert r.status_code == 404

    def test_student_diploma_view_pending(self, diploma_pending):
        tok = diploma_pending["student"]["token"]
        r = requests.get(f"{API}/diplomas/{diploma_pending['code']}", headers=auth_h(tok))
        assert r.status_code == 200
        assert r.json()["status"] == "pendiente"

    def test_admin_lists_diploma(self, admin, diploma_pending):
        r = requests.get(f"{API}/diplomas", headers=auth_h(admin["token"]))
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert diploma_pending["id"] in ids


class TestApproveRBAC:
    def test_student_cannot_approve(self, diploma_pending):
        tok = diploma_pending["student"]["token"]
        r = requests.post(f"{API}/diplomas/{diploma_pending['id']}/approve", headers=auth_h(tok))
        assert r.status_code == 403

    def test_docente_cannot_approve(self, admin, diploma_pending):
        # make a docente directly
        d_id = f"test-doc-i5-{uuid.uuid4().hex[:8]}"
        mongo.users.insert_one({"id": d_id, "email": f"delivered+docent{d_id}@resend.dev",
                                "nombre": "TEST_Doc", "apellidos": "Teach", "rut": "",
                                "role": "docente", "active": True,
                                "created_at": datetime.now(timezone.utc).isoformat()})
        tok = mint(d_id)
        r = requests.post(f"{API}/diplomas/{diploma_pending['id']}/approve", headers=auth_h(tok))
        assert r.status_code == 403


class TestApproveFlow:
    @pytest.fixture(scope="class")
    def approved(self, admin, diploma_pending):
        r = requests.post(f"{API}/diplomas/{diploma_pending['id']}/approve", headers=auth_h(admin["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "aprobado"
        assert d["approved_at"]
        assert d["verify_url"].endswith(f"/verificar/{diploma_pending['code']}")
        return {**diploma_pending, "approved": d}

    def test_second_approve_400(self, admin, approved):
        r = requests.post(f"{API}/diplomas/{approved['id']}/approve", headers=auth_h(admin["token"]))
        assert r.status_code == 400

    def test_owner_pdf(self, approved):
        tok = approved["student"]["token"]
        r = requests.get(f"{API}/diplomas/{approved['code']}/pdf", headers=auth_h(tok))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_other_student_pdf_404(self, approved):
        tok = approved["other"]["token"]
        r = requests.get(f"{API}/diplomas/{approved['code']}/pdf", headers=auth_h(tok))
        assert r.status_code == 404

    def test_staff_pdf(self, admin, approved):
        r = requests.get(f"{API}/diplomas/{approved['code']}/pdf", headers=auth_h(admin["token"]))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_public_pdf(self, approved):
        r = requests.get(f"{API}/public/diplomas/{approved['code']}/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_public_verify(self, approved):
        r = requests.get(f"{API}/public/verify/{approved['code']}")
        assert r.status_code == 200
        d = r.json()
        assert d["code"] == approved["code"]
        assert d["student_name"] == "TEST_i5A Owner"
        assert d["course_title"] == "TEST_i5_cert_course"
        assert d["approved_at"]

    def test_pdf_content_text_and_images(self, approved):
        r = requests.get(f"{API}/public/diplomas/{approved['code']}/pdf")
        assert r.status_code == 200
        doc = pymupdf.open(stream=r.content, filetype="pdf")
        text = "\n".join(p.get_text() for p in doc)
        for needed in ("TEST_i5A Owner", "TEST_i5_cert_course",
                       "Maximiliano Alcafuz Orellana", "Liliana Hernández Guerrero",
                       "Karolyne González Possamai", "Directora Académica", approved["code"]):
            assert needed in text, f"missing in PDF: {needed!r}\n--- extracted:\n{text}"
        # Images (template + QR, min 1)
        imgs = []
        for p in doc:
            imgs.extend(p.get_images(full=True))
        assert len(imgs) >= 1


class TestRejectFlow:
    @pytest.fixture(scope="class")
    def another_pending(self, admin, seed):
        """Second student passes exam to get a fresh pending diploma for reject testing."""
        stu = seed["students"][1]
        # module/final may already have been attempted? seed is module-scope so student B hasn't done it yet
        requests.post(f"{API}/modules/{seed['module']['id']}/complete", headers=auth_h(stu["token"]))
        r = requests.post(f"{API}/courses/{seed['course']['id']}/final-exam/submit",
                          headers=auth_h(stu["token"]),
                          json={"answers": {"fq1": "4"}, "tab_switches": 0, "paste_events": 0, "duration_sec": 5})
        assert r.status_code == 200, r.text
        code = r.json()["diploma_code"]
        d = mongo.diplomas.find_one({"code": code})
        return {"id": d["id"], "code": code}

    def test_reject_pending(self, admin, another_pending):
        r = requests.post(f"{API}/diplomas/{another_pending['id']}/reject",
                          headers=auth_h(admin["token"]), json={"reason": "TEST_reject"})
        assert r.status_code == 200
        d = mongo.diplomas.find_one({"id": another_pending["id"]})
        assert d["status"] == "rechazado"
        assert d["reject_reason"] == "TEST_reject"

    def test_reject_approved_400(self, admin, diploma_pending):
        # diploma_pending has been approved by TestApproveFlow (same module scope).
        r = requests.post(f"{API}/diplomas/{diploma_pending['id']}/reject",
                          headers=auth_h(admin["token"]), json={"reason": "nope"})
        assert r.status_code == 400


class TestSettingsAndPreview:
    def test_settings_names(self, admin, settings_snapshot):
        r = requests.get(f"{API}/settings", headers=auth_h(admin["token"]))
        assert r.status_code == 200
        s = r.json()
        # Only assert directora name per request (real names must not be changed by test)
        assert s.get("directora_name") == "Karolyne González Possamai", s.get("directora_name")

    def test_preview_default_template(self, admin):
        r = requests.post(f"{API}/settings/certificate-preview", headers=auth_h(admin["token"]))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_preview_with_custom_png_template(self, admin):
        # Create a tiny PNG via pymupdf
        import struct
        import zlib
        # Minimal 2x2 white PNG
        def make_png():
            sig = b"\x89PNG\r\n\x1a\n"
            def chunk(t, d):
                return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
            ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
            raw = b"\x00\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff"
            idat = zlib.compress(raw)
            return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

        files = {"file": ("tpl.png", make_png(), "image/png")}
        r = requests.post(f"{API}/files", headers=auth_h(admin["token"]), files=files)
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        # PUT settings with custom template
        s_now = requests.get(f"{API}/settings", headers=auth_h(admin["token"])).json()
        s_now["cert_template"] = {"file_id": fid, "file_name": "tpl.png", "content_type": "image/png"}
        r = requests.put(f"{API}/settings", headers=auth_h(admin["token"]), json=s_now)
        assert r.status_code == 200
        r = requests.post(f"{API}/settings/certificate-preview", headers=auth_h(admin["token"]))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        # Reset template
        s_now["cert_template"] = {}
        r = requests.put(f"{API}/settings", headers=auth_h(admin["token"]), json=s_now)
        assert r.status_code == 200
        assert (r.json().get("cert_template") or {}) == {}


class TestVerifyPage:
    def test_verify_invalid(self):
        r = requests.get(f"{API}/public/verify/IBA-ZZZZ-ZZZZ")
        assert r.status_code == 404
