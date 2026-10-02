"""Backend tests for final-exam copy-protection:
- SubmitIn accepts copy_attempts
- POST /courses/{id}/final-exam/submit persists behavior.copy_attempts
- GET /submissions (admin) returns copy_attempts in behavior
- Regression: module submit still accepts copy_attempts (= 0 by default)
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]


def mint(uid):
    return pyjwt.encode(
        {"sub": uid, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        JWT_SECRET, algorithm="HS256")


def hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin():
    u = mongo.users.find_one({"role": "admin", "active": True})
    assert u, "need seeded admin"
    return u


@pytest.fixture(scope="module")
def course(admin):
    cid = "TEST_cg_course"
    mid = "TEST_cg_mod"
    now = datetime.now(timezone.utc).isoformat()
    final_quiz = {
        "pass_score": 50,
        "draw_count": 2,
        "questions": [
            {"id": "fq1", "type": "mc", "text": "2+2?", "options": ["3", "4"], "correct": 1},
            {"id": "fq2", "type": "mc", "text": "Sky?", "options": ["Blue", "Green"], "correct": 0},
        ],
    }
    mod_quiz = {
        "pass_score": 50,
        "draw_count": 1,
        "questions": [
            {"id": "mq1", "type": "mc", "text": "1+1?", "options": ["2", "3"], "correct": 0},
        ],
    }
    mongo.courses.update_one({"id": cid}, {"$set": {
        "id": cid, "title": "TEST_cg Course", "description": "", "code": "T", "hours": 0,
        "auto_enroll": False, "published": True, "price": 0, "summary": "",
        "modality": "", "image_file_id": "", "show_on_landing": False,
        "teacher_id": admin["id"], "created_at": now,
        "final_exam": final_quiz,
    }}, upsert=True)
    mongo.modules.update_one({"id": mid}, {"$set": {
        "id": mid, "course_id": cid, "title": "TEST_cg Mod", "order": 1,
        "video_url": "", "duration_sec": 0, "min_time_sec": 0,
        "materials": [], "tasks": [], "quiz": mod_quiz,
    }}, upsert=True)
    yield {"course_id": cid, "module_id": mid}
    mongo.courses.delete_many({"id": cid})
    mongo.modules.delete_many({"course_id": cid})
    mongo.enrollments.delete_many({"course_id": cid})
    mongo.submissions.delete_many({"course_id": cid})
    mongo.quiz_draws.delete_many({"course_id": cid})


@pytest.fixture(scope="module")
def student(course):
    uid = str(uuid.uuid4())
    mongo.users.insert_one({
        "id": uid, "email": f"delivered+TEST_cg_{uid[:6]}@resend.dev",
        "nombre": "TEST", "apellidos": "Copy", "rut": "", "role": "estudiante",
        "active": True, "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": None, "signup_method": "manual"})
    mongo.enrollments.insert_one({
        "id": "TEST_cg_enr_" + uid, "user_id": uid, "course_id": course["course_id"],
        "method": "manual", "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "completed_modules": [course["module_id"]],  # all modules complete
        "final_passed": False, "completed_at": None,
        "completed_tasks": {}, "module_results": {course["module_id"]: 100}})
    yield uid
    mongo.users.delete_one({"id": uid})
    mongo.enrollments.delete_many({"user_id": uid})
    mongo.submissions.delete_many({"user_id": uid})
    mongo.quiz_draws.delete_many({"user_id": uid})


def test_submit_in_accepts_copy_attempts(course, student):
    """POST final-exam/submit should accept copy_attempts and persist it."""
    tok = mint(student)
    # Fetch exam first to establish any draw
    r = requests.get(f"{API}/courses/{course['course_id']}/final-exam", headers=hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    quiz = r.json()
    assert quiz["questions"], "exam must have questions"
    # Answer with correct for both to pass
    answers = {}
    for q in quiz["questions"]:
        # options returned without `correct` so just pick 0; score may fail — not relevant for copy_attempts persistence
        answers[q["id"]] = 0
    payload = {"answers": answers, "tab_switches": 2, "paste_events": 1, "copy_attempts": 7, "duration_sec": 42}
    r = requests.post(f"{API}/courses/{course['course_id']}/final-exam/submit",
                      json=payload, headers=hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "status" in data

    # Verify persisted in mongo
    sub = mongo.submissions.find_one({"user_id": student, "course_id": course["course_id"], "kind": "final"},
                                     sort=[("created_at", -1)])
    assert sub, "submission not persisted"
    assert sub["behavior"]["copy_attempts"] == 7, sub["behavior"]
    assert sub["behavior"]["tab_switches"] == 2
    assert sub["behavior"]["paste_events"] == 1


def test_admin_submissions_includes_copy_attempts(admin, course, student):
    """GET /submissions returns behavior.copy_attempts for admin UI tile."""
    tok = mint(admin["id"])
    r = requests.get(f"{API}/submissions", params={"course_id": course["course_id"]},
                     headers=hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    subs = r.json()
    assert subs, "no submissions returned"
    final = [s for s in subs if s.get("kind") == "final" and s["user_id"] == student]
    assert final, "no final submission for student"
    s = final[0]
    assert s["behavior"]["copy_attempts"] == 7
    # No mongo _id leak
    assert "_id" not in s


def test_copy_attempts_defaults_to_zero(course):
    """SubmitIn: copy_attempts defaults to 0 (regression for module submit without the field)."""
    # Create fresh student
    uid = str(uuid.uuid4())
    mongo.users.insert_one({
        "id": uid, "email": f"delivered+TEST_cg2_{uid[:6]}@resend.dev",
        "nombre": "TEST", "apellidos": "Zero", "rut": "", "role": "estudiante", "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(), "last_login": None, "signup_method": "manual"})
    mongo.enrollments.insert_one({
        "id": "TEST_cg_enr2_" + uid, "user_id": uid, "course_id": course["course_id"],
        "method": "manual", "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "completed_modules": [], "final_passed": False, "completed_at": None,
        "completed_tasks": {course["module_id"]: {}}, "module_results": {}})
    try:
        tok = mint(uid)
        # Submit module without copy_attempts field at all
        payload = {"answers": {"mq1": 0}, "tab_switches": 0, "paste_events": 0, "duration_sec": 10}
        r = requests.post(f"{API}/modules/{course['module_id']}/submit",
                          json=payload, headers=hdr(tok), timeout=15)
        assert r.status_code == 200, r.text
        sub = mongo.submissions.find_one({"user_id": uid, "module_id": course["module_id"]})
        assert sub["behavior"]["copy_attempts"] == 0
    finally:
        mongo.users.delete_one({"id": uid})
        mongo.enrollments.delete_many({"user_id": uid})
        mongo.submissions.delete_many({"user_id": uid})
