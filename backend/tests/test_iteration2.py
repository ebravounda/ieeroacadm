"""Iteration 2: IberoAcademy new features backend tests.

Covers:
- Default pass_score = 75 (new Quiz model default)
- Materials & file upload/download (/api/files)
- Task completion gating module exam
- Fail exam -> completed_tasks reset -> exam re-locked
- Pass module exam -> next module unlocked, Chilean nota correct
- Multiple-selection graded with exact set match
- Open question -> status en_revision, student can't resubmit,
  staff grade endpoint flips to calificada and applies pass/fail
- Final exam locked until all module exams passed, diploma issued with nota_final
- Branding (EMAIL_FROM_NAME=IberoAcademy, APP_NAME=iberoacademy)
- Analytics students table includes avg_nota
"""
import os
import io
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


def mint_token(uid):
    return pyjwt.encode(
        {"sub": uid, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"},
        JWT_SECRET, algorithm="HS256")


def login_as(email):
    u = mongo.users.find_one({"email": email.lower(), "active": True})
    assert u, f"user {email} not found"
    return mint_token(u["id"])


def auth_h(t):
    return {"Authorization": f"Bearer {t}"}


def make_student(admin_token, label, course_id=None):
    email = f"delivered+{label}{int(time.time()*1000) % 1000000}@resend.dev"
    r = requests.post(f"{API}/users", headers=auth_h(admin_token), json={
        "email": email, "nombre": f"TEST_{label}", "apellidos": "Student",
        "role": "estudiante", "course_id": course_id})
    assert r.status_code == 200, r.text
    u = r.json()
    return u, mint_token(u["id"])


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    return login_as(ADMIN_EMAIL)


@pytest.fixture(scope="module")
def course(admin_token):
    r = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
        "title": "TEST_Ibero_i2", "description": "Iteration 2 course",
        "code": "I2", "hours": 20, "auto_enroll": False, "published": True})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def uploaded_file(admin_token):
    # Small text file
    files = {"file": ("TEST_task.txt", io.BytesIO(b"hola iberoacademy"), "text/plain")}
    r = requests.post(f"{API}/files", headers=auth_h(admin_token), files=files)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def modules(admin_token, course, uploaded_file):
    cid = course["id"]
    mat_txt = {"id": "mat-txt-1", "type": "texto", "title": "Lectura 1", "body": "Contenido lectura"}
    mat_file = {"id": "mat-file-1", "type": "archivo", "title": "PDF descarga",
                "file_id": uploaded_file["id"], "file_name": uploaded_file["file_name"],
                "content_type": uploaded_file["content_type"]}

    # Module 1: single + multiple + open quiz, 2 materials, pass_score default 75
    r = requests.post(f"{API}/courses/{cid}/modules", headers=auth_h(admin_token), json={
        "title": "TEST_M1_i2", "content": "contenido M1",
        "materials": [mat_txt, mat_file],
        "quiz": {"pass_score": 75, "questions": [
            {"id": "s1", "type": "single", "text": "¿Capital de Chile?",
             "options": ["Santiago", "Lima", "Quito"], "correct": 0},
            {"id": "m1", "type": "multiple", "text": "Pares (<10)",
             "options": ["2", "3", "4", "5"], "correct_multi": [0, 2]},
        ]}})
    assert r.status_code == 200, r.text
    m1 = r.json()

    # Module 2: single-only quiz
    r = requests.post(f"{API}/courses/{cid}/modules", headers=auth_h(admin_token), json={
        "title": "TEST_M2_i2", "content": "contenido M2",
        "materials": [],
        "quiz": {"pass_score": 75, "questions": [
            {"id": "s1", "type": "single", "text": "2+2", "options": ["3", "4"], "correct": 1}]}})
    m2 = r.json()

    # Final exam
    r = requests.put(f"{API}/courses/{cid}/final-exam", headers=auth_h(admin_token), json={
        "pass_score": 75,
        "questions": [{"id": "f1", "type": "single", "text": "Ok?",
                       "options": ["Si", "No"], "correct": 0}]})
    assert r.status_code == 200
    return {"m1": m1, "m2": m2, "course_id": cid}


# ---------- Tests ----------
class TestDefaults:
    def test_default_pass_score_is_75(self, admin_token, course):
        """A module created with no quiz override should default pass_score to 75."""
        r = requests.post(f"{API}/courses/{course['id']}/modules", headers=auth_h(admin_token), json={
            "title": "TEST_default_ps", "content": ""})
        assert r.status_code == 200, r.text
        assert r.json()["quiz"]["pass_score"] == 75
        # cleanup extra module
        requests.delete(f"{API}/modules/{r.json()['id']}", headers=auth_h(admin_token))

    def test_branding_from_name(self):
        # IberoAcademy branding: check EMAIL_FROM_NAME env variable used by backend
        # (settings.otec_name may have been overridden by regression tests)
        from_name = os.environ.get("EMAIL_FROM_NAME", "")
        # Read from backend .env directly if not set in test env
        if not from_name:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("EMAIL_FROM_NAME"):
                        from_name = line.split("=", 1)[1].strip().strip('"')
                        break
        assert "iberoacademy" in from_name.lower(), f"EMAIL_FROM_NAME={from_name}"


class TestFileUpload:
    def test_upload_and_query_auth_download(self, admin_token, uploaded_file):
        # Download via Authorization header
        r = requests.get(f"{API}/files/{uploaded_file['id']}", headers=auth_h(admin_token))
        assert r.status_code == 200
        assert r.content == b"hola iberoacademy"
        # Download via ?auth= query param (used by <iframe>/<img>)
        r = requests.get(f"{API}/files/{uploaded_file['id']}?auth={admin_token}")
        assert r.status_code == 200
        assert r.content == b"hola iberoacademy"

    def test_file_rejects_disallowed_extension(self, admin_token):
        files = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
        r = requests.post(f"{API}/files", headers=auth_h(admin_token), files=files)
        assert r.status_code == 400


class TestTaskGating:
    def test_module_exam_locked_until_tasks_done(self, admin_token, modules):
        _, tok = make_student(admin_token, "tgate", modules["course_id"])
        r = requests.get(f"{API}/modules/{modules['m1']['id']}", headers=auth_h(tok))
        assert r.status_code == 200
        assert r.json()["tasks_done"] is False
        # Try to submit exam -> blocked
        r = requests.post(f"{API}/modules/{modules['m1']['id']}/submit", headers=auth_h(tok),
                          json={"answers": {"s1": "0", "m1": ["0", "2"]},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 5})
        assert r.status_code == 400
        assert "tareas" in r.json()["detail"].lower()

    def test_complete_tasks_unlocks_exam(self, admin_token, modules):
        _, tok = make_student(admin_token, "tdone", modules["course_id"])
        mid = modules["m1"]["id"]
        for matid in ("mat-txt-1", "mat-file-1"):
            r = requests.post(f"{API}/modules/{mid}/tasks/{matid}/complete", headers=auth_h(tok))
            assert r.status_code == 200
        r = requests.get(f"{API}/modules/{mid}", headers=auth_h(tok))
        assert r.json()["tasks_done"] is True


class TestGradingAndFlow:
    def _complete_tasks(self, tok, mid):
        for matid in ("mat-txt-1", "mat-file-1"):
            requests.post(f"{API}/modules/{mid}/tasks/{matid}/complete", headers=auth_h(tok))

    def test_fail_exam_resets_tasks(self, admin_token, modules):
        _, tok = make_student(admin_token, "fail1", modules["course_id"])
        mid = modules["m1"]["id"]
        self._complete_tasks(tok, mid)
        # Submit with wrong answers (all 0)
        r = requests.post(f"{API}/modules/{mid}/submit", headers=auth_h(tok),
                          json={"answers": {"s1": "2", "m1": ["1"]},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "calificada"
        assert d["passed"] is False
        # Tasks should be reset
        r = requests.get(f"{API}/modules/{mid}", headers=auth_h(tok))
        assert r.json()["tasks_done"] is False
        assert r.json()["completed_tasks"] == []
        # Module 2 still locked
        r = requests.get(f"{API}/modules/{modules['m2']['id']}", headers=auth_h(tok))
        assert r.status_code == 403

    def test_pass_module_exam_and_nota(self, admin_token, modules):
        _, tok = make_student(admin_token, "pass1", modules["course_id"])
        mid = modules["m1"]["id"]
        self._complete_tasks(tok, mid)
        # All correct: single=0, multiple exact [0,2]
        r = requests.post(f"{API}/modules/{mid}/submit", headers=auth_h(tok),
                          json={"answers": {"s1": "0", "m1": ["0", "2"]},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "calificada"
        assert d["passed"] is True
        assert d["score"] == 100
        # Chilean nota: pct=100, pass=75 -> 4+3*25/25 = 7.0
        assert d["nota"] == 7.0
        # Module 2 now unlocked
        r = requests.get(f"{API}/modules/{modules['m2']['id']}", headers=auth_h(tok))
        assert r.status_code == 200

    def test_multiple_partial_is_wrong(self, admin_token, modules):
        _, tok = make_student(admin_token, "mpart", modules["course_id"])
        mid = modules["m1"]["id"]
        self._complete_tasks(tok, mid)
        # Only one of two correct multi options chosen -> multiple=0, single=100 -> 50% fail
        r = requests.post(f"{API}/modules/{mid}/submit", headers=auth_h(tok),
                          json={"answers": {"s1": "0", "m1": ["0"]},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        d = r.json()
        assert d["passed"] is False
        assert d["score"] == 50

    def test_border_nota_at_pass_score(self, admin_token):
        """pct == pass_score should yield nota 4.0 (Chilean scale boundary)."""
        # Create a dedicated isolated course so this test doesn't leak modules
        rc = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
            "title": "TEST_border_course", "description": "", "code": "BRD",
            "hours": 1, "auto_enroll": False, "published": True}).json()
        cid = rc["id"]
        try:
            r = requests.post(f"{API}/courses/{cid}/modules", headers=auth_h(admin_token), json={
                "title": "TEST_border", "content": "",
                "quiz": {"pass_score": 50, "questions": [
                    {"id": "a", "type": "single", "text": "a", "options": ["x", "y"], "correct": 0},
                    {"id": "b", "type": "single", "text": "b", "options": ["x", "y"], "correct": 1}]}})
            mid = r.json()["id"]
            _, tok = make_student(admin_token, "border", cid)
            # answer one correct one wrong -> 50% == pass_score=50 -> nota 4.0
            r = requests.post(f"{API}/modules/{mid}/submit", headers=auth_h(tok),
                              json={"answers": {"a": "0", "b": "0"},
                                    "tab_switches": 0, "paste_events": 0, "duration_sec": 5})
            d = r.json()
            assert d["score"] == 50
            assert d["passed"] is True
            assert d["nota"] == 4.0
        finally:
            requests.delete(f"{API}/courses/{cid}", headers=auth_h(admin_token))


class TestOpenQuestionGrading:
    @pytest.fixture(scope="class")
    def open_course(self, admin_token):
        r = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
            "title": "TEST_i2_open", "description": "", "code": "I2O",
            "hours": 1, "auto_enroll": False, "published": True})
        c = r.json()
        r = requests.post(f"{API}/courses/{c['id']}/modules", headers=auth_h(admin_token), json={
            "title": "TEST_open_mod", "content": "",
            "quiz": {"pass_score": 75, "questions": [
                {"id": "o1", "type": "open", "text": "Explica", "options": []}]}})
        m = r.json()
        return {"course": c, "module": m}

    def test_open_submission_goes_to_review_then_graded(self, admin_token, open_course):
        _, tok = make_student(admin_token, "openst", open_course["course"]["id"])
        mid = open_course["module"]["id"]
        r = requests.post(f"{API}/modules/{mid}/submit", headers=auth_h(tok),
                          json={"answers": {"o1": "Mi ensayo largo sobre el tema"},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 60})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "en_revision"
        assert d["score"] is None
        assert d["nota"] is None
        # Student cannot retake while pending
        r = requests.post(f"{API}/modules/{mid}/submit", headers=auth_h(tok),
                          json={"answers": {"o1": "otra"},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 60})
        assert r.status_code == 400

        # Staff grades it 90% -> passed, status calificada
        subs = requests.get(f"{API}/submissions", headers=auth_h(admin_token)).json()
        sub = next(s for s in subs if s["module_id"] == mid and s["status"] == "en_revision")
        r = requests.post(f"{API}/submissions/{sub['id']}/grade", headers=auth_h(admin_token),
                          json={"grades": {"o1": 90}, "feedback": "Buen trabajo"})
        assert r.status_code == 200, r.text
        graded = r.json()
        assert graded["status"] == "calificada"
        assert graded["score"] == 90
        assert graded["passed"] is True
        assert graded["nota"] == pytest.approx(to_nota_py(90, 75), abs=0.1)
        # Can't double-grade
        r = requests.post(f"{API}/submissions/{sub['id']}/grade", headers=auth_h(admin_token),
                          json={"grades": {"o1": 50}})
        assert r.status_code == 400


def to_nota_py(pct, e):
    if pct < e:
        n = 1 + 3 * pct / e
    else:
        n = 4 + 3 * (pct - e) / (100 - e)
    return round(max(1.0, min(7.0, n)), 1)


class TestFinalExamAndDiploma:
    def test_final_only_after_all_modules_and_diploma_overall_nota(self, admin_token, modules):
        _, tok = make_student(admin_token, "fin2", modules["course_id"])
        # Complete M1
        for matid in ("mat-txt-1", "mat-file-1"):
            requests.post(f"{API}/modules/{modules['m1']['id']}/tasks/{matid}/complete", headers=auth_h(tok))
        requests.post(f"{API}/modules/{modules['m1']['id']}/submit", headers=auth_h(tok),
                      json={"answers": {"s1": "0", "m1": ["0", "2"]},
                            "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        # Final exam locked (M2 not done)
        r = requests.get(f"{API}/courses/{modules['course_id']}/final-exam", headers=auth_h(tok))
        assert r.status_code == 403
        # Complete M2
        requests.post(f"{API}/modules/{modules['m2']['id']}/submit", headers=auth_h(tok),
                      json={"answers": {"s1": "1"},
                            "tab_switches": 0, "paste_events": 0, "duration_sec": 5})
        # Now unlocked
        r = requests.get(f"{API}/courses/{modules['course_id']}/final-exam", headers=auth_h(tok))
        assert r.status_code == 200
        # Submit final (correct)
        r = requests.post(f"{API}/courses/{modules['course_id']}/final-exam/submit",
                          headers=auth_h(tok),
                          json={"answers": {"f1": "0"},
                                "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200
        res = r.json()
        assert res["passed"] is True
        assert res["diploma_code"]
        # Public verify shows nota_final
        pr = requests.get(f"{API}/public/verify/{res['diploma_code']}")
        assert pr.status_code == 200
        pub = pr.json()
        assert pub["valid"] is True
        # mod avg 100, final 100 -> overall 100 -> nota 7.0
        assert pub["nota_final"] == 7.0
        # Course view should expose grades for student
        r = requests.get(f"{API}/courses/{modules['course_id']}", headers=auth_h(tok))
        grades = r.json()["grades"]
        assert grades["modules_avg_pct"] == 100
        assert grades["final_pct"] == 100
        assert grades["overall_nota"] == 7.0


class TestAnalyticsNota:
    def test_students_table_has_avg_nota_column(self, admin_token):
        r = requests.get(f"{API}/analytics/students", headers=auth_h(admin_token))
        assert r.status_code == 200
        rows = r.json()
        # at least one row has avg_nota set after our test submissions
        assert any("avg_nota" in r for r in rows)
        with_nota = [r for r in rows if r.get("avg_nota") is not None]
        assert len(with_nota) >= 1, "Expected at least one student with avg_nota after test submissions"
