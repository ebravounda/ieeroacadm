"""Tests for POST /api/courses/{id}/import-modules

Covers dry_run preview, actual creation (ordering, materials types, section_id),
exclusion of evaluations and course-tail headings, 400 on bad text, and 403 for
students.
"""
import os
import time
from pathlib import Path

import pytest
import requests

from backend_test import API, auth_h, make_student, mongo, login_as


@pytest.fixture(scope="module")
def admin_token():
    return login_as("info@iberoacademy.cl")

SAMPLE = Path(__file__).parent / "sample_import.txt"


@pytest.fixture(scope="module")
def sample_text():
    return SAMPLE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def import_course(admin_token):
    r = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
        "title": "TEST_IMPORT", "description": "Course for import tests",
        "code": "TIMP", "hours": 10, "auto_enroll": False, "published": False})
    assert r.status_code == 200, r.text
    c = r.json()
    yield c
    # Cleanup: delete modules and course
    mongo.modules.delete_many({"course_id": c["id"]})
    try:
        requests.delete(f"{API}/courses/{c['id']}", headers=auth_h(admin_token))
    except Exception:
        pass
    mongo.courses.delete_one({"id": c["id"]})


class TestImportModules:
    def test_bad_text_returns_400(self, admin_token, import_course):
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": "No hay modulos aqui, solo texto normal.", "dry_run": True})
        assert r.status_code == 400, r.text

    def test_dry_run_returns_preview_no_create(self, admin_token, import_course, sample_text):
        before = mongo.modules.count_documents({"course_id": import_course["id"]})
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": sample_text, "dry_run": True})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "modules" in data
        mods = data["modules"]
        assert len(mods) == 3, f"Expected 3 modules, got {len(mods)}: {[m['title'] for m in mods]}"
        titles = [m["title"] for m in mods]
        assert "Competencias digitales y organización del entorno de trabajo" in titles[0]
        assert "Microsoft Word" in titles[1]
        assert "Evaluación práctica final" in titles[2]
        # Module 1 sections: Lección 1, Lección 2, Actividad práctica, Material audiovisual
        s1 = mods[0]["sections"]
        assert any("Lección 1" in s for s in s1)
        assert any("Lección 2" in s for s in s1)
        assert any("Actividad" in s for s in s1)
        assert any("Material audiovisual" in s for s in s1)
        # Module 2 sections
        s2 = mods[1]["sections"]
        assert any("Lección 1" in s for s in s2)
        assert any("Recursos" in s for s in s2)
        # Module 3 (Evaluación práctica final) tareas
        s3 = mods[2]["sections"]
        assert any("Tarea 1" in s for s in s3), s3
        assert any("Tarea 2" in s for s in s3), s3
        # No creation
        after = mongo.modules.count_documents({"course_id": import_course["id"]})
        assert after == before

    def test_create_modules_persisted(self, admin_token, import_course, sample_text):
        # Create one preexisting module to test ordering continues
        r = requests.post(f"{API}/courses/{import_course['id']}/modules",
                          headers=auth_h(admin_token),
                          json={"title": "TEST_PreExisting", "content": "pre"})
        assert r.status_code == 200
        pre_order = r.json()["order"]
        before = mongo.modules.count_documents({"course_id": import_course["id"]})

        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": sample_text, "dry_run": False})
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 3
        after = mongo.modules.count_documents({"course_id": import_course["id"]})
        assert after == before + 3

        mods = list(mongo.modules.find({"course_id": import_course["id"]}).sort("order", 1))
        # Ordering should continue after preexisting
        assert mods[-3]["order"] == pre_order + 1
        assert mods[-2]["order"] == pre_order + 2
        assert mods[-1]["order"] == pre_order + 3

        m1, m2, m3 = mods[-3], mods[-2], mods[-1]

        # Module 1 checks
        assert "Competencias digitales" in m1["title"]
        sec_titles = [s["title"] for s in m1["sections"]]
        assert any("Lección 1" in t for t in sec_titles)
        assert any("Material audiovisual" in t for t in sec_titles)
        # Materials: each section has section_id and type texto; youtube link -> video
        mats = m1["materials"]
        for mat in mats:
            assert mat.get("section_id"), f"Missing section_id in material: {mat}"
        video_mats = [m for m in mats if m["type"] == "video"]
        assert len(video_mats) >= 1, "Youtube URL should create a video material"
        assert "youtube.com" in video_mats[0]["url"]

        # No material body should contain evaluation content
        for m in (m1, m2, m3):
            for mat in m["materials"]:
                body = (mat.get("body") or "") + " " + (mat.get("title") or "")
                assert "Respuesta correcta" not in body, f"Evaluation leaked into {m['title']}: {body[:100]}"
                assert "Evaluaciones por módulo" not in body, f"Course-tail leaked: {body[:100]}"
                assert "CERTIFICACIÓN" not in body
                assert "METODOLOGÍA" not in body

        # Module 2: Recursos section should exist, no evaluation
        s2_titles = [s["title"] for s in m2["sections"]]
        assert any("Recursos" in t for t in s2_titles)
        assert not any("Evaluación" in t for t in s2_titles)

        # Module 3: Tareas (treated as lesson-like sections)
        s3_titles = [s["title"] for s in m3["sections"]]
        assert any("Tarea 1" in t for t in s3_titles), s3_titles
        assert any("Tarea 2" in t for t in s3_titles), s3_titles

    def test_student_forbidden(self, admin_token, import_course, sample_text):
        _, tok = make_student(admin_token, "imp")
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(tok),
                          json={"text": sample_text, "dry_run": True})
        assert r.status_code == 403

    def test_course_not_found(self, admin_token, sample_text):
        r = requests.post(f"{API}/courses/nonexistent-id/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": sample_text, "dry_run": True})
        assert r.status_code == 404
