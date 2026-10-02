"""Backend tests for admin Integrations panel (Resend/OpenAI/Flow/Cron)."""
import os
import asyncio
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://learn-progress-ai-2.preview.emergentagent.com"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "ed0.2580@gmail.com"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CRON_SECRET_ENV = os.environ.get("WEBHOOK_CRON_SECRET", "")


def _admin_token():
    from motor.motor_asyncio import AsyncIOMotorClient
    async def go():
        r = requests.post(f"{API}/auth/request-code", json={"email": ADMIN_EMAIL})
        assert r.status_code == 200, r.text
        c = AsyncIOMotorClient(MONGO_URL)
        db = c[DB_NAME]
        # wait a moment for insert
        for _ in range(10):
            rec = await db.otp_codes.find_one({"email": ADMIN_EMAIL})
            if rec:
                break
            await asyncio.sleep(0.3)
        assert rec, "OTP not created"
        code = rec["code"]
        r2 = requests.post(f"{API}/auth/verify-code", json={"email": ADMIN_EMAIL, "code": code})
        assert r2.status_code == 200, r2.text
        return r2.json()["token"]
    return asyncio.run(go())


_cached_admin_token = None


def _get_admin_token_cached():
    global _cached_admin_token
    if _cached_admin_token is None:
        _cached_admin_token = _admin_token()
    return _cached_admin_token


@pytest.fixture(scope="session")
def admin_headers():
    return {"Authorization": f"Bearer {_get_admin_token_cached()}"}


@pytest.fixture(scope="session")
def student_headers():
    h = {"Authorization": f"Bearer {_get_admin_token_cached()}"}
    email = "delivered+testintg@resend.dev"
    requests.post(f"{API}/users", headers=h, json={
        "email": email, "nombre": "TEST", "apellidos": "Student", "role": "estudiante"})
    # login as student (passwordless)
    from motor.motor_asyncio import AsyncIOMotorClient
    async def go():
        requests.post(f"{API}/auth/request-code", json={"email": email})
        c = AsyncIOMotorClient(MONGO_URL)
        db = c[DB_NAME]
        for _ in range(10):
            rec = await db.otp_codes.find_one({"email": email})
            if rec:
                break
            await asyncio.sleep(0.3)
        r2 = requests.post(f"{API}/auth/verify-code", json={"email": email, "code": rec["code"]})
        return r2.json()["token"]
    stok = asyncio.run(go())
    return {"Authorization": f"Bearer {stok}"}


# ---------- Admin-only guard ----------
class TestGuards:
    def test_unauth_get_401(self):
        r = requests.get(f"{API}/admin/integrations")
        assert r.status_code in (401, 403)

    def test_student_forbidden(self, student_headers):
        r = requests.get(f"{API}/admin/integrations", headers=student_headers)
        assert r.status_code == 403

    def test_admin_ok(self, admin_headers):
        r = requests.get(f"{API}/admin/integrations", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) >= {"email", "ai", "payments", "cron"}
        assert "lines" in d["cron"]


# ---------- Email (Resend) ----------
class TestEmail:
    def test_save_resend_key_returns_hint_not_full(self, admin_headers):
        key = "re_FAKEKEY_1234567890abcd1234"  # ends with 1234
        r = requests.put(f"{API}/admin/integrations", headers=admin_headers,
                         json={"resend_api_key": key, "mail_from": "no-reply@example.com", "email_from_name": "Test"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"]["key_hint"] == "••••1234"
        assert key not in r.text
        assert d["email"]["mail_from"] == "no-reply@example.com"

    def test_invalid_mail_from_400(self, admin_headers):
        r = requests.put(f"{API}/admin/integrations", headers=admin_headers,
                         json={"mail_from": "invalid-no-at"})
        assert r.status_code == 400

    def test_empty_key_keeps_existing(self, admin_headers):
        r = requests.put(f"{API}/admin/integrations", headers=admin_headers,
                         json={"resend_api_key": "", "email_from_name": "Test2"})
        assert r.status_code == 200
        assert r.json()["email"]["key_hint"] == "••••1234"  # retained

    def test_clear_removes_key(self, admin_headers):
        r = requests.put(f"{API}/admin/integrations", headers=admin_headers,
                         json={"clear": ["resend_api_key"]})
        assert r.status_code == 200
        assert r.json()["email"]["key_hint"] == ""

    def test_test_email_with_fallback(self, admin_headers):
        # After clearing key, Emergent fallback should work
        r = requests.post(f"{API}/admin/integrations/test-email", headers=admin_headers,
                         json={"to": "delivered@resend.dev"})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True


# ---------- AI (OpenAI) ----------
class TestAI:
    def test_save_openai_key_hint(self, admin_headers):
        r = requests.put(f"{API}/admin/integrations", headers=admin_headers,
                         json={"openai_api_key": "sk-FAKEOPENAIKEY_abcd9999", "openai_model": "gpt-4o-mini"})
        assert r.status_code == 200
        d = r.json()
        assert d["ai"]["key_hint"] == "••••9999"
        assert d["ai"]["openai_model"] == "gpt-4o-mini"

    def test_openai_test_fake_key_returns_502(self, admin_headers):
        r = requests.post(f"{API}/admin/integrations/test-ai", headers=admin_headers)
        assert r.status_code == 502
        # Response body may be rewritten by ingress on 502; status code is sufficient

    def test_clear_openai_and_fallback_ok(self, admin_headers):
        r = requests.put(f"{API}/admin/integrations", headers=admin_headers,
                         json={"clear": ["openai_api_key"]})
        assert r.status_code == 200
        assert r.json()["ai"]["key_hint"] == ""
        # Now the Emergent fallback should succeed
        r2 = requests.post(f"{API}/admin/integrations/test-ai", headers=admin_headers)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("ok") is True


# ---------- Cron ----------
class TestCron:
    def test_cron_lines_present(self, admin_headers):
        r = requests.get(f"{API}/admin/integrations", headers=admin_headers)
        d = r.json()
        lines = d["cron"]["lines"]
        assert len(lines) == 3
        for l in lines:
            assert "/api/cron/" in l["line"]

    def test_cron_no_auth_401(self):
        r = requests.post(f"{API}/cron/class-reminders", json={})
        assert r.status_code == 401

    def test_cron_with_env_secret_ok(self):
        if not CRON_SECRET_ENV:
            pytest.skip("No WEBHOOK_CRON_SECRET in env")
        r = requests.post(f"{API}/cron/class-reminders",
                          headers={"Authorization": f"Bearer {CRON_SECRET_ENV}"}, json={})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True


# ---------- Cleanup ----------
def test_zz_cleanup():
    """Remove all test data: fake keys and the integrations doc created during tests."""
    from motor.motor_asyncio import AsyncIOMotorClient
    async def go():
        c = AsyncIOMotorClient(MONGO_URL)
        db = c[DB_NAME]
        # Clean test student
        await db.users.delete_many({"email": "delivered+testintg@resend.dev"})
        # Remove integrations doc entirely (didn't exist before tests)
        await db.settings.delete_one({"id": "integrations"})
        # Remove any flow keys we might have set (none set here but defensive)
        await db.settings.update_one({"id": "payments"},
                                     {"$unset": {"flow_api_key": "", "flow_secret_key": ""}})
        s = await db.settings.find_one({"id": "integrations"})
        assert s is None
    asyncio.run(go())
