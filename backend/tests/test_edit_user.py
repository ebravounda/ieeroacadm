"""Backend tests for PUT /api/users/{id} edit (nombre/apellidos/rut)."""
import os
import time
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://learn-progress-ai-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "info@iberoacademy.cl"


def _db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


async def _get_code(email):
    for _ in range(20):
        rec = await _db().otp_codes.find_one({"email": email})
        if rec and rec.get("code"):
            return rec["code"]
        await asyncio.sleep(0.3)
    return None


def _login(email):
    r = requests.post(f"{API}/auth/request-code", json={"email": email})
    assert r.status_code == 200, r.text
    code = asyncio.get_event_loop().run_until_complete(_get_code(email))
    assert code, "OTP code not found"
    r = requests.post(f"{API}/auth/verify-code", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def test_user(admin_headers):
    payload = {
        "email": "delivered+edit@resend.dev",
        "nombre": "Original",
        "apellidos": "User",
        "rut": "11.111.111-1",
        "role": "estudiante",
    }
    # cleanup if exists
    r = requests.get(f"{API}/users", headers=admin_headers)
    for u in r.json():
        if u["email"] == payload["email"]:
            # just use existing - but reset values
            requests.put(f"{API}/users/{u['id']}", headers=admin_headers,
                         json={"nombre": "Original", "apellidos": "User", "rut": "11.111.111-1"})
            yield u
            # cleanup via mongo
            asyncio.get_event_loop().run_until_complete(_db().users.delete_one({"id": u["id"]}))
            return
    r = requests.post(f"{API}/users", headers=admin_headers, json=payload)
    assert r.status_code == 200, r.text
    user = r.json()
    yield user
    asyncio.get_event_loop().run_until_complete(_db().users.delete_one({"id": user["id"]}))


def test_update_user_name_and_rut(admin_headers, test_user):
    r = requests.put(f"{API}/users/{test_user['id']}", headers=admin_headers,
                     json={"nombre": "  Nuevo  ", "apellidos": "  Apellido ", "rut": " 22.222.222-2 "})
    assert r.status_code == 200, r.text
    data = r.json()
    # Values must be trimmed
    assert data["nombre"] == "Nuevo"
    assert data["apellidos"] == "Apellido"
    assert data["rut"] == "22.222.222-2"
    # Verify persisted via GET
    r2 = requests.get(f"{API}/users", headers=admin_headers)
    row = next(u for u in r2.json() if u["id"] == test_user["id"])
    assert row["nombre"] == "Nuevo"
    assert row["rut"] == "22.222.222-2"


def test_update_user_empty_nombre_returns_400(admin_headers, test_user):
    r = requests.put(f"{API}/users/{test_user['id']}", headers=admin_headers,
                     json={"nombre": "   "})
    assert r.status_code == 400, r.text


def test_update_user_requires_admin(test_user):
    # Create a non-admin user and login
    admin_hdrs = {"Authorization": f"Bearer {_login(ADMIN_EMAIL)}"}
    student_email = "delivered+editstudent@resend.dev"
    # ensure student exists
    r = requests.get(f"{API}/users", headers=admin_hdrs)
    student = next((u for u in r.json() if u["email"] == student_email), None)
    if not student:
        r = requests.post(f"{API}/users", headers=admin_hdrs, json={
            "email": student_email, "nombre": "Stu", "apellidos": "Dent",
            "rut": "", "role": "estudiante"})
        assert r.status_code == 200, r.text
        student = r.json()
    try:
        token = _login(student_email)
        r = requests.put(f"{API}/users/{test_user['id']}",
                         headers={"Authorization": f"Bearer {token}"},
                         json={"nombre": "Hacker"})
        assert r.status_code in (401, 403), r.text
    finally:
        asyncio.get_event_loop().run_until_complete(_db().users.delete_one({"id": student["id"]}))


def test_update_user_no_auth(test_user):
    r = requests.put(f"{API}/users/{test_user['id']}", json={"nombre": "X"})
    assert r.status_code in (401, 403)


def test_toggle_active_still_works(admin_headers, test_user):
    # Desactivar
    r = requests.put(f"{API}/users/{test_user['id']}", headers=admin_headers, json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False
    # Activar
    r = requests.put(f"{API}/users/{test_user['id']}", headers=admin_headers, json={"active": True})
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_matricular_still_works(admin_headers, test_user):
    # Get a course
    r = requests.get(f"{API}/courses", headers=admin_headers)
    courses = r.json()
    if not courses:
        pytest.skip("No courses available")
    cid = courses[0]["id"]
    r = requests.post(f"{API}/enrollments", headers=admin_headers,
                      json={"user_id": test_user["id"], "course_id": cid})
    assert r.status_code == 200, r.text
    # cleanup
    enr = r.json()
    asyncio.get_event_loop().run_until_complete(_db().enrollments.delete_one({"id": enr["id"]}))
