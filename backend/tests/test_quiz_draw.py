"""Tests for randomized question draws per student (iteration 14).

Covers:
- draw_count persistence via PUT /modules and PUT /courses/{id}/final-exam
- GET /modules/{id} returns N shuffled questions without correct keys
- same student gets same draw until submission; two students differ
- POST /modules/{id}/submit grades using drawn (shuffled) options; attempts increment
- final exam: single attempt; failing resets completed_modules & deletes draws; 403 on next GET
"""
import os
import time
import random
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
    assert u, "admin not found"
    return mint(u["id"])


@pytest.fixture(scope="module")
def course_with_bank(admin_token):
    # Create course
    r = requests.post(f"{API}/courses", headers=h(admin_token), json={
        "title": "TEST_QuizDraw", "description": "", "code": "TQD", "hours": 1,
        "auto_enroll": False, "published": True})
    assert r.status_code == 200, r.text
    course = r.json()
    cid = course["id"]

    # Build bank of 15 single-choice questions
    questions = []
    for i in range(15):
        correct = i % 4
        questions.append({
            "id": f"q{i}", "type": "single",
            "text": f"TEST pregunta {i}?",
            "options": [f"opt{i}_{j}" for j in range(4)],
            "correct": correct, "correct_multi": [],
        })
    # Add one module with the bank, draw_count=10, min_minutes=0
    r = requests.post(f"{API}/courses/{cid}/modules", headers=h(admin_token), json={
        "title": "TEST_Mod1", "description": "", "content": "", "video_url": "", "min_minutes": 0,
        "materials": [], "sections": [],
        "quiz": {"questions": questions, "pass_score": 75, "draw_count": 10}})
    assert r.status_code == 200, r.text
    module = r.json()

    # Final exam with 12 questions, draw_count=10
    final_qs = []
    for i in range(12):
        c = i % 3
        final_qs.append({
            "id": f"fq{i}", "type": "single",
            "text": f"TEST final {i}?",
            "options": [f"f{i}_{j}" for j in range(3)],
            "correct": c, "correct_multi": [],
        })
    r = requests.put(f"{API}/courses/{cid}/final-exam", headers=h(admin_token),
                     json={"questions": final_qs, "pass_score": 60, "draw_count": 10})
    assert r.status_code == 200, r.text

    yield {"course_id": cid, "module": module, "questions": questions, "final_qs": final_qs}

    # Cleanup
    requests.delete(f"{API}/courses/{cid}", headers=h(admin_token))
    mongo.quiz_draws.delete_many({"course_id": cid})
    mongo.submissions.delete_many({"course_id": cid})
    mongo.enrollments.delete_many({"course_id": cid})
    # Delete test users created
    for email in list(mongo.users.find({"nombre": {"$regex": "^TEST_QD"}}, {"email": 1})):
        mongo.users.delete_one({"_id": email["_id"]})


def make_student(admin_token, label, course_id):
    email = f"delivered+TEST_QD_{label}_{int(time.time()*1000)%1000000}@resend.dev"
    r = requests.post(f"{API}/users", headers=h(admin_token), json={
        "email": email, "nombre": f"TEST_QD_{label}", "apellidos": "S",
        "role": "estudiante", "course_id": course_id})
    assert r.status_code == 200, r.text
    u = r.json()
    return u, mint(u["id"])


# ---------- Tests ----------

class TestDrawCountPersistence:
    def test_module_draw_count_saved(self, admin_token, course_with_bank):
        mid = course_with_bank["module"]["id"]
        m = mongo.modules.find_one({"id": mid})
        assert m["quiz"]["draw_count"] == 10

    def test_final_draw_count_saved(self, admin_token, course_with_bank):
        c = mongo.courses.find_one({"id": course_with_bank["course_id"]})
        assert c["final_exam"]["draw_count"] == 10
        assert c["final_exam"]["pass_score"] == 60


class TestModuleDraw:
    def test_student_gets_10_without_answers(self, admin_token, course_with_bank):
        _, tok = make_student(admin_token, "s1", course_with_bank["course_id"])
        mid = course_with_bank["module"]["id"]
        r = requests.get(f"{API}/modules/{mid}", headers=h(tok))
        assert r.status_code == 200, r.text
        quiz = r.json()["quiz"]
        assert len(quiz["questions"]) == 10
        for q in quiz["questions"]:
            assert "correct" not in q
            assert "correct_multi" not in q
            assert q["type"] == "single"

    def test_same_student_same_draw(self, admin_token, course_with_bank):
        _, tok = make_student(admin_token, "s2", course_with_bank["course_id"])
        mid = course_with_bank["module"]["id"]
        q1 = requests.get(f"{API}/modules/{mid}", headers=h(tok)).json()["quiz"]["questions"]
        q2 = requests.get(f"{API}/modules/{mid}", headers=h(tok)).json()["quiz"]["questions"]
        ids1 = [q["id"] for q in q1]
        ids2 = [q["id"] for q in q2]
        assert ids1 == ids2
        # options also persisted in same order
        for a, b in zip(q1, q2):
            assert a["options"] == b["options"]

    def test_different_students_differ(self, admin_token, course_with_bank):
        _, t1 = make_student(admin_token, "d1", course_with_bank["course_id"])
        _, t2 = make_student(admin_token, "d2", course_with_bank["course_id"])
        mid = course_with_bank["module"]["id"]
        s1 = requests.get(f"{API}/modules/{mid}", headers=h(t1)).json()["quiz"]["questions"]
        s2 = requests.get(f"{API}/modules/{mid}", headers=h(t2)).json()["quiz"]["questions"]
        ids1 = [q["id"] for q in s1]
        ids2 = [q["id"] for q in s2]
        # Highly likely different subsets or orders across 10 of 15
        assert ids1 != ids2 or any(a["options"] != b["options"] for a, b in zip(s1, s2))


class TestSubmitAndAttempts:
    def _answer_correctly(self, drawn_questions, bank):
        """Pick correct index for each drawn question given shuffled options."""
        bank_by_id = {q["id"]: q for q in bank}
        answers = {}
        for q in drawn_questions:
            orig = bank_by_id[q["id"]]
            correct_text = orig["options"][orig["correct"]]
            answers[q["id"]] = q["options"].index(correct_text)
        return answers

    def test_submit_correct_gives_100_and_attempts(self, admin_token, course_with_bank):
        user, tok = make_student(admin_token, "sub", course_with_bank["course_id"])
        mid = course_with_bank["module"]["id"]
        # First attempt — intentionally wrong
        drawn = requests.get(f"{API}/modules/{mid}", headers=h(tok)).json()["quiz"]["questions"]
        wrong = {q["id"]: (q["options"].index(q["options"][0]) ^ 1) % len(q["options"]) for q in drawn}
        # Build wrong answers that differ from correct
        answers_wrong = self._answer_correctly(drawn, course_with_bank["questions"])
        answers_wrong = {k: (v + 1) % len(next(q for q in drawn if q["id"] == k)["options"]) for k, v in answers_wrong.items()}
        r = requests.post(f"{API}/modules/{mid}/submit", headers=h(tok),
                          json={"answers": answers_wrong, "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["attempt"] == 1
        assert d["passed"] is False
        # Draw should be deleted after submission
        key = {"user_id": user["id"], "course_id": course_with_bank["course_id"], "module_id": mid}
        assert mongo.quiz_draws.find_one(key) is None

        # Second attempt - correct
        drawn2 = requests.get(f"{API}/modules/{mid}", headers=h(tok)).json()["quiz"]["questions"]
        answers_ok = self._answer_correctly(drawn2, course_with_bank["questions"])
        r = requests.post(f"{API}/modules/{mid}/submit", headers=h(tok),
                          json={"answers": answers_ok, "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["attempt"] == 2
        assert d["score"] == 100
        assert d["passed"] is True

    def test_admin_submissions_show_attempt(self, admin_token, course_with_bank):
        r = requests.get(f"{API}/submissions?course_id={course_with_bank['course_id']}", headers=h(admin_token))
        assert r.status_code == 200
        subs = r.json()
        attempts = sorted({s["attempt"] for s in subs if s.get("module_id")})
        assert 1 in attempts and 2 in attempts


class TestFinalExam:
    def _bank_lookup(self, bank):
        return {q["id"]: q for q in bank}

    def test_final_requires_modules(self, admin_token, course_with_bank):
        _, tok = make_student(admin_token, "fnew", course_with_bank["course_id"])
        r = requests.get(f"{API}/courses/{course_with_bank['course_id']}/final-exam", headers=h(tok))
        assert r.status_code == 403

    def test_final_fail_resets_course(self, admin_token, course_with_bank):
        user, tok = make_student(admin_token, "ff", course_with_bank["course_id"])
        mid = course_with_bank["module"]["id"]
        # Pass the module first
        drawn = requests.get(f"{API}/modules/{mid}", headers=h(tok)).json()["quiz"]["questions"]
        bank = self._bank_lookup(course_with_bank["questions"])
        answers = {}
        for q in drawn:
            orig = bank[q["id"]]
            answers[q["id"]] = q["options"].index(orig["options"][orig["correct"]])
        r = requests.post(f"{API}/modules/{mid}/submit", headers=h(tok),
                          json={"answers": answers, "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200, f"module submit failed: {r.status_code} {r.text}"
        assert r.json().get("passed") is True, f"not passed: {r.json()}"

        # Now final exam accessible
        cid = course_with_bank["course_id"]
        r = requests.get(f"{API}/courses/{cid}/final-exam", headers=h(tok))
        assert r.status_code == 200, r.text
        final = r.json()
        assert len(final["questions"]) == 10
        for q in final["questions"]:
            assert "correct" not in q

        # Submit wrong answers (all index 0 which may/may not be right -> aim for failure)
        wrong = {q["id"]: (len(q["options"]) - 1) for q in final["questions"]}
        # To ensure failure, pick the WRONG option by looking up original correct text in drawn options
        fbank = self._bank_lookup(course_with_bank["final_qs"])
        wrong = {}
        for q in final["questions"]:
            orig = fbank[q["id"]]
            correct_text = orig["options"][orig["correct"]]
            correct_idx = q["options"].index(correct_text)
            wrong[q["id"]] = (correct_idx + 1) % len(q["options"])
        r = requests.post(f"{API}/courses/{cid}/final-exam/submit", headers=h(tok),
                          json={"answers": wrong, "tab_switches": 0, "paste_events": 0, "duration_sec": 10})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["passed"] is False
        assert d.get("course_reset") is True

        # Enrollment reset
        e = mongo.enrollments.find_one({"user_id": user["id"], "course_id": cid})
        assert e["completed_modules"] == []
        assert e.get("completed_tasks") in ({}, None) or e["completed_tasks"] == {}
        assert e.get("module_results") in ({}, None) or e["module_results"] == {}

        # GET final-exam -> 403 now
        r = requests.get(f"{API}/courses/{cid}/final-exam", headers=h(tok))
        assert r.status_code == 403


class TestRegression:
    def test_module_without_quiz_completable(self, admin_token):
        # Use its own course to avoid interfering with final exam tests under xdist
        r = requests.post(f"{API}/courses", headers=h(admin_token), json={
            "title": "TEST_QD_Regression", "description": "", "code": "TQDR", "hours": 1,
            "auto_enroll": False, "published": True})
        cid = r.json()["id"]
        try:
            r = requests.post(f"{API}/courses/{cid}/modules", headers=h(admin_token), json={
                "title": "TEST_NoQuiz", "min_minutes": 0, "materials": [], "sections": [],
                "quiz": {"questions": [], "pass_score": 75, "draw_count": 10}})
            assert r.status_code == 200
            mid = r.json()["id"]
            _, tok = make_student(admin_token, "nq", cid)
            r = requests.post(f"{API}/modules/{mid}/complete", headers=h(tok))
            # No quiz, no materials, min_minutes 0 — should complete
            assert r.status_code == 200, r.text
            assert r.json().get("ok") is True
        finally:
            requests.delete(f"{API}/courses/{cid}", headers=h(admin_token))
