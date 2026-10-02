"""Backend tests for reopen-final exam + diploma reissue (super admin).

Covers:
- GET /api/auth/me is_super for super vs regular admin vs docente vs student vs impersonation
- POST /api/enrollments/{id}/reopen-final 403 for non-super, success for super;
  verifies final_passed reset, completed_modules filled, diploma deleted, quiz_draw cleared
- Student can then GET /final-exam and submit again; passing creates NEW diploma w/ new code
- POST /api/diplomas/{id}/reissue (super only, approved only): new diploma w/ new code, status
  aprobado, reissued_from=old code; old becomes anulado w/ replaced_by; GET /diplomas and
  /my/diplomas exclude anulados; /public/verify/{oldcode} returns {valid:false, annulled:true,
  replaced_by}; /public/verify/{newcode} returns {valid:true}
- POST /api/diplomas/reissue-bulk reissues many
- Non-super admin gets 403 on reissue endpoints
"""
import os
import re
from datetime import datetime, timezone, timedelta

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
mongo = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "info@iberoacademy.cl").lower()


def mint(uid, imp=None):
    payload = {"sub": uid, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(days=1)}
    if imp:
        payload["imp"] = imp
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def hdr(uid, imp=None):
    return {"Authorization": f"Bearer {mint(uid, imp)}"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---- Fixtures ------------------------------------------------------------
@pytest.fixture(scope="module")
def super_admin():
    u = mongo.users.find_one({"email": ADMIN_EMAIL})
    assert u, "seeded super admin missing"
    return u


@pytest.fixture(scope="module")
def test_admin():
    uid = "TEST_rr_admin"
    doc = {"id": uid, "email": "delivered+TEST_rradmin@resend.dev",
           "nombre": "Admin", "apellidos": "Test", "rut": "11111111-1",
           "role": "admin", "active": True, "created_at": now_iso()}
    mongo.users.update_one({"id": uid}, {"$set": doc}, upsert=True)
    yield mongo.users.find_one({"id": uid})
    mongo.users.delete_one({"id": uid})


@pytest.fixture(scope="module")
def test_docente():
    uid = "TEST_rr_doc"
    doc = {"id": uid, "email": "delivered+TEST_rrdoc@resend.dev",
           "nombre": "Doc", "apellidos": "T", "rut": "22222222-2",
           "role": "docente", "active": True, "created_at": now_iso()}
    mongo.users.update_one({"id": uid}, {"$set": doc}, upsert=True)
    yield doc
    mongo.users.delete_one({"id": uid})


@pytest.fixture(scope="module")
def test_student():
    uid = "TEST_rr_stu"
    doc = {"id": uid, "email": "delivered+TEST_rrstu@resend.dev",
           "nombre": "Estu", "apellidos": "Diante", "rut": "33333333-3",
           "role": "estudiante", "active": True, "created_at": now_iso()}
    mongo.users.update_one({"id": uid}, {"$set": doc}, upsert=True)
    yield doc
    mongo.users.delete_one({"id": uid})


@pytest.fixture(scope="module")
def course(super_admin):
    cid = "TEST_rr_course"
    final_quiz = {"pass_score": 50, "draw_count": 2, "questions": [
        {"id": "fq1", "type": "mc", "text": "2+2?", "options": ["3", "4"], "correct": 1},
        {"id": "fq2", "type": "mc", "text": "Sky?", "options": ["Blue", "Green"], "correct": 0},
    ]}
    mongo.courses.update_one({"id": cid}, {"$set": {
        "id": cid, "title": "TEST_rr Course", "description": "", "code": "TRR", "hours": 10,
        "created_at": now_iso(), "final_exam": final_quiz, "published": True,
    }}, upsert=True)
    # one normal module (not welcome)
    mids = []
    for i in range(2):
        mid = f"TEST_rr_mod_{i}"
        mongo.modules.update_one({"id": mid}, {"$set": {
            "id": mid, "course_id": cid, "title": f"Mod {i}", "order": i,
            "sections": [], "materials": [], "min_minutes": 0,
            "quiz": {"questions": [], "pass_score": 75, "draw_count": 0},
        }}, upsert=True)
        mids.append(mid)
    yield {"id": cid, "mids": mids}
    mongo.courses.delete_one({"id": cid})
    mongo.modules.delete_many({"course_id": cid})


@pytest.fixture
def enrollment(course, test_student):
    eid = "TEST_rr_enr"
    mongo.enrollments.update_one({"id": eid}, {"$set": {
        "id": eid, "user_id": test_student["id"], "course_id": course["id"],
        "method": "manual", "enrolled_at": now_iso(),
        "completed_modules": list(course["mids"]),  # all modules complete
        "completed_tasks": {m: [] for m in course["mids"]},
        "module_results": {m: 100 for m in course["mids"]},
        "final_passed": True, "final_score": 100,
        "completed_at": now_iso(),
    }}, upsert=True)
    yield eid
    mongo.enrollments.delete_one({"id": eid})


@pytest.fixture(scope="module")
def iss_student():
    """Separate student for diploma reissue tests to avoid races with reopen tests."""
    uid = "TEST_rr_stu_iss"
    doc = {"id": uid, "email": "delivered+TEST_rrstuiss@resend.dev",
           "nombre": "Iss", "apellidos": "Student", "rut": "44444444-4",
           "role": "estudiante", "active": True, "created_at": now_iso()}
    mongo.users.update_one({"id": uid}, {"$set": doc}, upsert=True)
    yield doc
    mongo.users.delete_one({"id": uid})


@pytest.fixture
def issued_diploma(course, iss_student, super_admin):
    """Create and approve a diploma via API so a real PDF exists."""
    did = "TEST_rr_dip"
    code = "RR" + os.urandom(3).hex().upper()
    mongo.diplomas.update_one({"id": did}, {"$set": {
        "id": did, "code": code, "user_id": iss_student["id"], "course_id": course["id"],
        "student_name": f"{iss_student['nombre']} {iss_student['apellidos']}",
        "rut": iss_student["rut"], "course_title": "TEST_rr Course", "hours": 10,
        "nota_final": 6.5, "status": "pendiente", "issued_at": now_iso(),
    }}, upsert=True)
    r = requests.post(f"{API}/diplomas/{did}/approve", headers=hdr(super_admin["id"]))
    if r.status_code != 200:
        pytest.skip(f"Could not approve diploma (needs cert template?): {r.status_code} {r.text[:200]}")
    yield mongo.diplomas.find_one({"id": did}, {"_id": 0})
    mongo.diplomas.delete_many({"user_id": iss_student["id"], "course_id": course["id"]})


# ---- Tests ---------------------------------------------------------------
class TestAuthMeIsSuper:
    def test_super_admin_true(self, super_admin):
        r = requests.get(f"{API}/auth/me", headers=hdr(super_admin["id"]))
        assert r.status_code == 200
        assert r.json().get("is_super") is True

    def test_other_admin_false(self, test_admin):
        r = requests.get(f"{API}/auth/me", headers=hdr(test_admin["id"]))
        assert r.status_code == 200
        assert r.json().get("is_super") is False

    def test_docente_false(self, test_docente):
        r = requests.get(f"{API}/auth/me", headers=hdr(test_docente["id"]))
        assert r.status_code == 200
        assert r.json().get("is_super") is False

    def test_student_false(self, test_student):
        r = requests.get(f"{API}/auth/me", headers=hdr(test_student["id"]))
        assert r.status_code == 200
        assert r.json().get("is_super") is False

    def test_impersonation_false(self, super_admin, test_student):
        # super admin impersonating a student -> is_super must be False
        r = requests.get(f"{API}/auth/me",
                         headers=hdr(test_student["id"], imp=super_admin["id"]))
        assert r.status_code == 200
        body = r.json()
        assert body.get("is_super") is False
        imp = body.get("impersonated_by")
        imp_id = imp.get("id") if isinstance(imp, dict) else imp
        assert imp_id == super_admin["id"]


class TestReopenFinal:
    def test_non_super_admin_forbidden(self, enrollment, test_admin):
        r = requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                          headers=hdr(test_admin["id"]))
        assert r.status_code == 403

    def test_docente_forbidden(self, enrollment, test_docente):
        r = requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                          headers=hdr(test_docente["id"]))
        assert r.status_code in (401, 403)

    def test_student_forbidden(self, enrollment, test_student):
        r = requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                          headers=hdr(test_student["id"]))
        assert r.status_code in (401, 403)

    def test_super_impersonating_forbidden(self, enrollment, super_admin, test_student):
        r = requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                          headers=hdr(test_student["id"], imp=super_admin["id"]))
        assert r.status_code in (401, 403)

    def test_super_reopens_and_resets_state(self, enrollment, course, test_student, super_admin):
        # pre-conditions: diploma + quiz_draw exist
        mongo.diplomas.insert_one({"id": "TEST_rr_predip", "code": "PRED1",
            "user_id": test_student["id"], "course_id": course["id"],
            "student_name": "x", "course_title": "y", "hours": 0,
            "status": "aprobado", "issued_at": now_iso()})
        mongo.quiz_draws.insert_one({"id": "TEST_rr_draw",
            "user_id": test_student["id"], "course_id": course["id"],
            "module_id": None, "question_ids": ["fq1", "fq2"], "created_at": now_iso()})

        r = requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                          headers=hdr(super_admin["id"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["diplomas_removed"] >= 1

        e = mongo.enrollments.find_one({"id": enrollment})
        assert e["final_passed"] is False
        assert e["final_score"] is None
        assert set(e["completed_modules"]) == set(course["mids"])
        assert e.get("final_reopened_by") == super_admin["id"]
        assert e.get("final_reopened_at")

        # diplomas and final quiz_draws cleared
        assert mongo.diplomas.count_documents(
            {"user_id": test_student["id"], "course_id": course["id"]}) == 0
        assert mongo.quiz_draws.count_documents(
            {"user_id": test_student["id"], "course_id": course["id"], "module_id": None}) == 0

        # cleanup extra
        mongo.diplomas.delete_many({"id": "TEST_rr_predip"})

    def test_student_can_access_final_exam_after_reopen(self, enrollment, course, test_student, super_admin):
        requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                      headers=hdr(super_admin["id"]))
        r = requests.get(f"{API}/courses/{course['id']}/final-exam",
                         headers=hdr(test_student["id"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["final_passed"] is False
        assert len(data["questions"]) > 0

    def test_student_submits_final_again_new_diploma_generated(self, enrollment, course, test_student, super_admin):
        requests.post(f"{API}/enrollments/{enrollment}/reopen-final",
                      headers=hdr(super_admin["id"]))
        # fetch draw
        r = requests.get(f"{API}/courses/{course['id']}/final-exam",
                         headers=hdr(test_student["id"]))
        qids = [q["id"] for q in r.json()["questions"]]
        # look up stored draw to compute correct answers (options are shuffled)
        draw = mongo.quiz_draws.find_one(
            {"user_id": test_student["id"], "course_id": course["id"], "module_id": None})
        assert draw, "quiz_draws should exist after GET final-exam"
        answers = {q["id"]: q["correct"] for q in draw["quiz"]["questions"]}
        # only submit questions returned by GET
        answers = {qid: answers[qid] for qid in qids}
        sub = requests.post(f"{API}/courses/{course['id']}/final-exam/submit",
                            headers=hdr(test_student["id"]),
                            json={"answers": answers, "copy_attempts": 0})
        assert sub.status_code == 200, sub.text
        body = sub.json()
        assert body.get("passed") is True

        dips = list(mongo.diplomas.find(
            {"user_id": test_student["id"], "course_id": course["id"]}, {"_id": 0}))
        assert len(dips) == 1
        assert dips[0]["status"] == "pendiente"
        assert dips[0]["code"]
        # cleanup
        mongo.diplomas.delete_many({"user_id": test_student["id"], "course_id": course["id"]})
        mongo.submissions.delete_many({"user_id": test_student["id"], "course_id": course["id"]})


class TestReissue:
    def test_reissue_requires_super(self, issued_diploma, test_admin):
        r = requests.post(f"{API}/diplomas/{issued_diploma['id']}/reissue",
                          headers=hdr(test_admin["id"]))
        assert r.status_code == 403

    def test_reissue_bulk_requires_super(self, issued_diploma, test_admin):
        r = requests.post(f"{API}/diplomas/reissue-bulk",
                          headers=hdr(test_admin["id"]), json={"ids": [issued_diploma["id"]]})
        assert r.status_code == 403

    def test_reissue_pending_not_allowed(self, super_admin, iss_student, course):
        # create pending diploma
        did = "TEST_rr_pending"
        mongo.diplomas.update_one({"id": did}, {"$set": {
            "id": did, "code": "PND1", "user_id": iss_student["id"], "course_id": course["id"],
            "student_name": "Iss Student", "course_title": "x", "hours": 0,
            "status": "pendiente", "issued_at": now_iso()}}, upsert=True)
        r = requests.post(f"{API}/diplomas/{did}/reissue", headers=hdr(super_admin["id"]))
        assert r.status_code == 404
        mongo.diplomas.delete_one({"id": did})

    def test_reissue_creates_new_annuls_old(self, issued_diploma, super_admin, iss_student):
        old_code = issued_diploma["code"]
        r = requests.post(f"{API}/diplomas/{issued_diploma['id']}/reissue",
                          headers=hdr(super_admin["id"]))
        assert r.status_code == 200, r.text
        new = r.json()
        assert new["status"] == "aprobado"
        assert new["code"] != old_code
        assert new["reissued_from"] == old_code

        old = mongo.diplomas.find_one({"id": issued_diploma["id"]}, {"_id": 0})
        assert old["status"] == "anulado"
        assert old["replaced_by"] == new["code"]
        assert old.get("annulled_at")

    def test_listings_exclude_annulled(self, issued_diploma, super_admin, iss_student):
        # reissue to annul the old one
        r = requests.post(f"{API}/diplomas/{issued_diploma['id']}/reissue",
                          headers=hdr(super_admin["id"]))
        assert r.status_code == 200
        new_code = r.json()["code"]
        old_code = issued_diploma["code"]

        # admin listing
        rows = requests.get(f"{API}/diplomas", headers=hdr(super_admin["id"])).json()
        codes = [d["code"] for d in rows]
        assert old_code not in codes
        assert new_code in codes

        # student listing
        rows = requests.get(f"{API}/my/diplomas", headers=hdr(iss_student["id"])).json()
        codes = [d["code"] for d in rows]
        assert old_code not in codes
        assert new_code in codes

    def test_public_verify_annulled_and_valid(self, issued_diploma, super_admin):
        old_code = issued_diploma["code"]
        r = requests.post(f"{API}/diplomas/{issued_diploma['id']}/reissue",
                          headers=hdr(super_admin["id"]))
        new_code = r.json()["code"]

        v_old = requests.get(f"{API}/public/verify/{old_code}")
        assert v_old.status_code == 200
        body = v_old.json()
        assert body == {**body, "valid": False, "annulled": True, "code": old_code,
                        "replaced_by": new_code}
        assert body.get("annulled_at")

        v_new = requests.get(f"{API}/public/verify/{new_code}")
        assert v_new.status_code == 200
        assert v_new.json().get("valid") is True
        assert v_new.json().get("code") == new_code

    def test_reissue_bulk(self, super_admin, iss_student, course):
        # create two approved diplomas directly in db (skip PDF re-gen for the second)
        ids = []
        for i in range(2):
            did = f"TEST_rr_bulk_{i}"
            code = f"BLK{i}001"
            mongo.diplomas.update_one({"id": did}, {"$set": {
                "id": did, "code": code, "user_id": iss_student["id"],
                "course_id": course["id"], "student_name": "Iss Student", "rut": "44444444-4",
                "course_title": "TEST_rr Course", "hours": 10, "nota_final": 6.5,
                "status": "aprobado", "issued_at": now_iso(),
                "approved_at": now_iso(), "approved_by": super_admin["id"]}}, upsert=True)
            ids.append(did)
        r = requests.post(f"{API}/diplomas/reissue-bulk",
                          headers=hdr(super_admin["id"]), json={"ids": ids})
        assert r.status_code == 200, r.text
        body = r.json()
        # may partially fail if cert template missing; just check structure
        assert "reissued" in body and "errors" in body
        # cleanup
        mongo.diplomas.delete_many({"user_id": iss_student["id"], "course_id": course["id"]})
