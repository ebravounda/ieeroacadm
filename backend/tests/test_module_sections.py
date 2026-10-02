"""Tests for module sections+materials (iteration 12).

Covers:
- POST/PUT module with sections[] and materials[] of all types (incl. 'presentacion')
- GET /api/modules/{id} returns sections and materials in order
- Legacy module (no sections, only materials) still returns coherent payload
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "info@iberoacademy.cl"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

db = MongoClient(MONGO_URL)[DB_NAME]


def _login(email):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/request-code", json={"email": email})
    assert r.status_code == 200, r.text
    code = db.otp_codes.find_one({"email": email}, sort=[("created_at", -1)])["code"]
    r = s.post(f"{BASE_URL}/api/auth/verify-code", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL)


@pytest.fixture(scope="module")
def course(admin):
    code = f"TEST_SEC_{uuid.uuid4().hex[:6]}"
    r = admin.post(f"{BASE_URL}/api/courses", json={"title": f"TEST_sections_{code}", "code": code, "hours": 1})
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    yield cid
    admin.delete(f"{BASE_URL}/api/courses/{cid}")


def test_create_module_with_sections_and_all_material_types(admin, course):
    payload = {
        "title": "TEST module with sections",
        "description": "d",
        "min_minutes": 0,
        "sections": [
            {"id": "sec-a", "title": "Introducción", "description": "Primera sección"},
            {"id": "sec-b", "title": "Práctica", "description": ""},
        ],
        "materials": [
            {"id": "m1", "type": "texto", "title": "Lectura 1", "body": "contenido", "section_id": "sec-a"},
            {"id": "m2", "type": "video", "title": "Video YT", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "section_id": "sec-a"},
            {"id": "m3", "type": "presentacion", "title": "Pres PDF", "section_id": "sec-b"},
            {"id": "m4", "type": "archivo", "title": "Doc", "section_id": "sec-b"},
            {"id": "m5", "type": "enlace", "title": "Link", "url": "https://example.com", "section_id": "sec-b"},
        ],
        "quiz": {"questions": [], "pass_score": 75},
    }
    r = admin.post(f"{BASE_URL}/api/courses/{course}/modules", json=payload)
    assert r.status_code in (200, 201), r.text
    mid = r.json()["id"]

    r = admin.get(f"{BASE_URL}/api/modules/{mid}")
    assert r.status_code == 200
    data = r.json()
    assert [s["title"] for s in data["sections"]] == ["Introducción", "Práctica"]
    assert [s["id"] for s in data["sections"]] == ["sec-a", "sec-b"]
    assert [m["type"] for m in data["materials"]] == ["texto", "video", "presentacion", "archivo", "enlace"]
    assert [m["section_id"] for m in data["materials"]] == ["sec-a", "sec-a", "sec-b", "sec-b", "sec-b"]
    assert data["materials"][1]["url"].endswith("dQw4w9WgXcQ")

    # Update: reorder sections and remove a material
    payload["sections"] = list(reversed(payload["sections"]))
    payload["materials"] = [m for m in payload["materials"] if m["id"] != "m4"]
    r = admin.put(f"{BASE_URL}/api/modules/{mid}", json=payload)
    assert r.status_code == 200, r.text

    r = admin.get(f"{BASE_URL}/api/modules/{mid}")
    data = r.json()
    assert [s["id"] for s in data["sections"]] == ["sec-b", "sec-a"]
    assert {m["id"] for m in data["materials"]} == {"m1", "m2", "m3", "m5"}


def test_legacy_module_without_sections(admin, course):
    payload = {
        "title": "TEST legacy module",
        "sections": [],
        "materials": [
            {"id": "lm1", "type": "texto", "title": "Legacy lectura", "body": "x", "section_id": ""},
        ],
        "quiz": {"questions": [], "pass_score": 75},
    }
    r = admin.post(f"{BASE_URL}/api/courses/{course}/modules", json=payload)
    assert r.status_code in (200, 201), r.text
    mid = r.json()["id"]
    r = admin.get(f"{BASE_URL}/api/modules/{mid}")
    data = r.json()
    assert data["sections"] == []
    assert len(data["materials"]) == 1
    assert data["materials"][0]["section_id"] == ""


def test_presentacion_material_type_accepted(admin, course):
    """Ensure Literal in Material allows 'presentacion'."""
    r = admin.post(f"{BASE_URL}/api/courses/{course}/modules", json={
        "title": "TEST pres only",
        "sections": [{"id": "s1", "title": "S", "description": ""}],
        "materials": [{"id": "p1", "type": "presentacion", "title": "P", "section_id": "s1"}],
    })
    assert r.status_code in (200, 201), r.text
