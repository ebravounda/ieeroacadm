"""Tests for Markdown course import (POST /api/courses/{id}/import-modules).

Validates normalization: # headings, **bold**, `code`, bullets, --- rules,
tables, backslash escapes, &#x20; entities, markdown links with utm_source,
and the broken 'Negrita.Lección\n2\. Formato' line.
"""
import os
from pathlib import Path

import pytest
import requests

from backend_test import API, auth_h, mongo, login_as

SAMPLE_MD = Path(__file__).parent / "sample_import_md.txt"
SAMPLE_PLAIN = Path(__file__).parent / "sample_import.txt"


@pytest.fixture(scope="module")
def admin_token():
    return login_as("info@iberoacademy.cl")


@pytest.fixture(scope="module")
def md_text():
    return SAMPLE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def plain_text():
    return SAMPLE_PLAIN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def import_course(admin_token):
    r = requests.post(f"{API}/courses", headers=auth_h(admin_token), json={
        "title": "TEST_IMPORT_MD", "description": "MD import tests",
        "code": "TIMPMD", "hours": 32, "auto_enroll": False, "published": False})
    assert r.status_code == 200, r.text
    c = r.json()
    yield c
    mongo.modules.delete_many({"course_id": c["id"]})
    try:
        requests.delete(f"{API}/courses/{c['id']}", headers=auth_h(admin_token))
    except Exception:
        pass
    mongo.courses.delete_one({"id": c["id"]})


EXPECTED_TITLES = [
    "Competencias digitales y organización del entorno de trabajo",
    "Microsoft Word aplicado al trabajo administrativo",
    "Microsoft Excel para la gestión administrativa",
    "Inteligencia Artificial aplicada a la gestión administrativa",
    "Evaluación práctica final",
]


class TestMarkdownImport:
    def test_md_dry_run_5_modules(self, admin_token, import_course, md_text):
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": md_text, "dry_run": True})
        assert r.status_code == 200, r.text
        mods = r.json()["modules"]
        titles = [m["title"] for m in mods]
        assert len(mods) == 5, f"Expected 5 modules, got {len(mods)}: {titles}"
        for expected, got in zip(EXPECTED_TITLES, titles):
            assert expected == got, f"Title mismatch: expected '{expected}' got '{got}'"

    def test_word_module_sections(self, admin_token, import_course, md_text):
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": md_text, "dry_run": True})
        mods = r.json()["modules"]
        word_mod = mods[1]
        assert "Word" in word_mod["title"]
        secs = word_mod["sections"]
        # Verify the broken line was repaired into "Lección 2. Formato de texto"
        assert any("Lección 2" in s and "Formato" in s for s in secs), (
            f"Expected 'Lección 2. Formato de texto' section, got: {secs}"
        )
        assert any("Recursos" in s for s in secs), f"Expected 'Recursos' section, got: {secs}"

    def test_plain_format_still_3_modules(self, admin_token, import_course, plain_text):
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": plain_text, "dry_run": True})
        assert r.status_code == 200, r.text
        mods = r.json()["modules"]
        assert len(mods) == 3, f"Expected 3 modules for plain format, got {len(mods)}"

    def test_md_create_and_verify_materials(self, admin_token, import_course, md_text):
        # Clear any previously created modules in this course first
        mongo.modules.delete_many({"course_id": import_course["id"]})
        r = requests.post(f"{API}/courses/{import_course['id']}/import-modules",
                          headers=auth_h(admin_token),
                          json={"text": md_text, "dry_run": False})
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 5

        mods = list(mongo.modules.find({"course_id": import_course["id"]}).sort("order", 1))
        assert len(mods) == 5
        titles = [m["title"] for m in mods]
        for expected, got in zip(EXPECTED_TITLES, titles):
            assert expected == got

        # Collect all materials
        all_mats = []
        for m in mods:
            for mat in m["materials"]:
                all_mats.append((m["title"], mat))

        FORBIDDEN = ["Respuesta correcta", "Evaluaciones por módulo", "**", "`", "&#x20;"]
        for mod_title, mat in all_mats:
            blob = " ".join(str(mat.get(k) or "") for k in ("title", "body", "url"))
            for bad in FORBIDDEN:
                assert bad not in blob, (
                    f"Material in '{mod_title}' contains forbidden token '{bad}': {blob[:200]}"
                )

        # Validate YouTube link in Module 1 Material audiovisual
        m1 = mods[0]
        videos_m1 = [x for x in m1["materials"] if x["type"] == "video"]
        assert len(videos_m1) >= 1, "Module 1 should have a youtube video material"
        v = videos_m1[0]
        assert "youtube.com" in v["url"]
        assert "utm_source" not in v["url"], f"utm not stripped: {v['url']}"
        assert "\\" not in v["url"], f"backslash not stripped: {v['url']}"
        # Title should be the markdown link text, not generic 'Video'
        assert "Windows" in v["title"] or "Explorador" in v["title"], (
            f"Expected link text as title, got '{v['title']}'"
        )

        # Module 3 (Excel): also youtube
        m3 = mods[2]
        v3 = [x for x in m3["materials"] if x["type"] == "video"]
        assert len(v3) >= 1
        assert "youtube.com" in v3[0]["url"]
        assert "utm_source" not in v3[0]["url"]

        # Module 2 (Word): support.microsoft.com links should be 'enlace'
        m2 = mods[1]
        enlaces = [x for x in m2["materials"] if x["type"] == "enlace"]
        assert any("support.microsoft.com" in e["url"] for e in enlaces), (
            f"Expected support.microsoft.com enlace in Word module, got: "
            f"{[(e.get('type'), e.get('url')) for e in m2['materials']]}"
        )
        for e in enlaces:
            if "support.microsoft.com" in e["url"]:
                assert "utm_source" not in e["url"]

        # Each material must have section_id
        for mod_title, mat in all_mats:
            assert mat.get("section_id"), f"Material missing section_id in {mod_title}: {mat}"
