"""Backend tests for new Landing + Payments (shop.py) features."""
import os
import hmac
import hashlib
import asyncio
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env", override=False)

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE + "/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def admin_token():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import create_token
    return create_token("test-admin-1")


@pytest.fixture(scope="module")
def admin_hdr():
    return {"Authorization": f"Bearer {admin_token()}"}


@pytest.fixture(scope="module")
def db():
    from motor.motor_asyncio import AsyncIOMotorClient
    c = AsyncIOMotorClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module", autouse=True)
def seed_test_data(db):
    """Seed test admin + test courses used by all tests, cleanup after."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import now_iso
    admin_email = "test-admin-1@resend.dev"
    _run(db.users.delete_many({"email": admin_email}))
    admin = {"id": "test-admin-1", "email": admin_email,
             "nombre": "TEST", "apellidos": "Admin", "role": "admin",
             "active": True, "created_at": now_iso()}
    c1 = {"id": "test-c1", "title": "TEST Prevención de Riesgos", "slug": "test-c1",
          "price": 49900, "published": True, "show_on_landing": True,
          "description": "TEST course", "created_at": now_iso()}
    c2 = {"id": "test-c2", "title": "TEST Curso Gratis", "slug": "test-c2",
          "price": 0, "published": True, "show_on_landing": True,
          "description": "TEST free", "created_at": now_iso()}
    _run(db.users.update_one({"id": admin["id"]}, {"$set": admin}, upsert=True))
    _run(db.courses.update_one({"id": c1["id"]}, {"$set": c1}, upsert=True))
    _run(db.courses.update_one({"id": c2["id"]}, {"$set": c2}, upsert=True))
    # Seed fake flow keys so paid-course tests can exercise the "Flow rejects fake" path
    _run(db.settings.update_one({"id": "payments"},
         {"$set": {"flow_env": "sandbox", "flow_api_key": "FAKE-KEY",
                   "flow_secret_key": "fakesecret123"}}, upsert=True))
    yield
    _run(db.courses.delete_many({"id": {"$in": ["test-c1", "test-c2"]}}))
    _run(db.users.delete_one({"id": "test-admin-1"}))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------- Public landing ----------
class TestPublicLanding:
    def test_landing_returns_courses(self):
        r = requests.get(f"{API}/public/landing")
        assert r.status_code == 200
        data = r.json()
        assert "slides" in data and "courses" in data
        ids = [c["id"] for c in data["courses"]]
        assert "test-c1" in ids and "test-c2" in ids
        c1 = next(c for c in data["courses"] if c["id"] == "test-c1")
        assert c1["price"] == 49900
        assert c1["title"].startswith("TEST")

    def test_public_image_404_for_unused(self):
        r = requests.get(f"{API}/public/images/nonexistent-file-id")
        assert r.status_code == 404


# ---------- Checkout: free & paid ----------
class TestCheckout:
    def test_checkout_rejects_without_accept_terms(self, db):
        email = "delivered+notos@resend.dev"
        _run(db.users.delete_many({"email": email}))
        r = requests.post(f"{API}/public/checkout", json={
            "course_id": "test-c2", "email": email,
            "nombre": "TEST_NoTOS", "apellidos": "Lander", "rut": "11.111.111-1"})
        assert r.status_code == 400, r.text
        assert "acept" in r.text.lower() and ("rminos" in r.text or "T\u00e9rminos" in r.text or "terminos" in r.text.lower())
        # explicit false also rejected
        r2 = requests.post(f"{API}/public/checkout", json={
            "course_id": "test-c2", "email": email, "accept_terms": False,
            "nombre": "TEST_NoTOS", "apellidos": "Lander", "rut": "11.111.111-1"})
        assert r2.status_code == 400
        # cleanup
        _run(db.users.delete_many({"email": email}))

    def test_free_course_enrolls(self, db):
        email = "delivered+freelander@resend.dev"
        _run(db.users.delete_many({"email": email}))
        _run(db.enrollments.delete_many({"user_id": {"$exists": True}, "course_id": "test-c2"}))
        r = requests.post(f"{API}/public/checkout", json={
            "course_id": "test-c2", "email": email, "accept_terms": True,
            "nombre": "TEST_Free", "apellidos": "Lander", "rut": "11.111.111-1"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("free") is True
        assert "order_id" in data
        # verify user+enrollment persisted
        user = _run(db.users.find_one({"email": email}, {"_id": 0}))
        assert user and user["role"] == "estudiante"
        assert user.get("terms_accepted_at"), "terms_accepted_at must be stored"
        enr = _run(db.enrollments.find_one({"user_id": user["id"], "course_id": "test-c2"}))
        assert enr is not None
        pay = _run(db.payments.find_one({"id": data["order_id"]}, {"_id": 0}))
        assert pay["status"] == "pagado" and pay["enrolled"] is True
        # cleanup
        _run(db.users.delete_many({"email": email}))
        _run(db.enrollments.delete_many({"user_id": user["id"]}))
        _run(db.payments.delete_many({"id": data["order_id"]}))

    def test_paid_course_with_fake_keys_returns_error_no_orphan(self, db):
        email = "delivered+paidtest@resend.dev"
        _run(db.users.delete_many({"email": email}))
        _run(db.payments.delete_many({"email": email}))
        before = _run(db.payments.count_documents({"email": email, "status": "pendiente"}))
        r = requests.post(f"{API}/public/checkout", json={
            "course_id": "test-c1", "email": email, "accept_terms": True,
            "nombre": "TEST_Paid", "apellidos": "Lander", "rut": "22.222.222-2"})
        # Flow rejects fake keys -> expect 400
        assert r.status_code == 400, r.text
        assert "Flow" in r.text or "rechaz" in r.text.lower()
        # No orphan pending payment
        after = _run(db.payments.count_documents({"email": email, "status": "pendiente"}))
        assert after == before, f"Orphan pending payment left: {before}->{after}"
        _run(db.users.delete_many({"email": email}))

    def test_paid_course_no_flow_keys_configured(self, db):
        """Temporarily remove flow keys -> expect 'no configurados' message."""
        orig = _run(db.settings.find_one({"id": "payments"}, {"_id": 0}))
        _run(db.settings.update_one({"id": "payments"}, {"$set": {"flow_api_key": "", "flow_secret_key": ""}}))
        try:
            email = "delivered+noconfig@resend.dev"
            _run(db.users.delete_many({"email": email}))
            r = requests.post(f"{API}/public/checkout", json={
                "course_id": "test-c1", "email": email, "accept_terms": True,
                "nombre": "TEST_NoConfig", "apellidos": "Lander", "rut": "33.333.333-3"})
            assert r.status_code == 503, r.text
            assert "configurad" in r.text.lower()
            # no orphan
            assert _run(db.payments.count_documents({"email": email, "status": "pendiente"})) == 0
            _run(db.users.delete_many({"email": email}))
        finally:
            if orig:
                _run(db.settings.update_one({"id": "payments"}, {"$set": {
                    "flow_api_key": orig.get("flow_api_key", ""),
                    "flow_secret_key": orig.get("flow_secret_key", "")}}))


# ---------- Flow endpoints ----------
class TestFlowEndpoints:
    def test_flow_confirm_unknown_token(self):
        r = requests.post(f"{API}/payments/flow/confirm", data={"token": "unknown-token"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_flow_return_redirects_303(self):
        r = requests.get(f"{API}/payments/flow/return", params={"token": "x"}, allow_redirects=False)
        assert r.status_code == 303
        assert "/pago/resultado?orden=" in r.headers.get("location", "")


# ---------- Flow signature ----------
class TestFlowSignature:
    def test_signed_matches_hmac(self):
        import sys as _sys
        _sys.path.insert(0, "/app/backend")
        import server  # noqa: F401  - initialize server first to avoid circular import
        from shop import signed
        params = {"b": "2", "a": "1", "z": "last"}
        secret = "mysecret"
        out = signed(params, secret)
        to_sign = "a1b2zlast"
        expected = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).hexdigest()
        assert out["s"] == expected


# ---------- Admin endpoints ----------
class TestAdminEndpoints:
    def test_payment_settings_masks_secret(self, admin_hdr):
        r = requests.get(f"{API}/admin/payment-settings", headers=admin_hdr)
        assert r.status_code == 200
        data = r.json()
        assert "flow_secret_key" not in data
        assert data.get("secret_set") is True
        assert data.get("secret_hint", "").startswith("••••")

    def test_landing_get(self, admin_hdr):
        r = requests.get(f"{API}/admin/landing", headers=admin_hdr)
        assert r.status_code == 200
        assert "slides" in r.json()

    def test_landing_put_and_get_slide(self, admin_hdr):
        slides = [{"id": "test-slide-1", "image_file_id": "", "title": "TEST Hero", "subtitle": "TEST Subtitle"}]
        r = requests.put(f"{API}/admin/landing", json={"slides": slides}, headers=admin_hdr)
        assert r.status_code == 200
        # public landing should reflect
        r2 = requests.get(f"{API}/public/landing")
        titles = [s["title"] for s in r2.json()["slides"]]
        assert "TEST Hero" in titles
        # cleanup
        requests.put(f"{API}/admin/landing", json={"slides": []}, headers=admin_hdr)

    def test_payments_list(self, admin_hdr):
        r = requests.get(f"{API}/payments", headers=admin_hdr)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_mark_paid_enrolls(self, db, admin_hdr):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import new_id, now_iso
        email = "delivered+markpaid@resend.dev"
        _run(db.users.delete_many({"email": email}))
        user = {"id": new_id(), "email": email, "nombre": "TEST_Mark", "apellidos": "Paid",
                "role": "estudiante", "active": True, "created_at": now_iso()}
        _run(db.users.insert_one(dict(user)))
        pay = {"id": new_id(), "order": f"IBA-{new_id()[:8].upper()}", "user_id": user["id"],
               "email": email, "student_name": "TEST_Mark Paid", "course_id": "test-c1",
               "course_title": "TEST Prevención de Riesgos", "amount": 49900,
               "status": "pendiente", "enrolled": False, "created_at": now_iso()}
        _run(db.payments.insert_one(dict(pay)))
        r = requests.post(f"{API}/payments/{pay['id']}/mark-paid", headers=admin_hdr)
        assert r.status_code == 200, r.text
        updated = _run(db.payments.find_one({"id": pay["id"]}, {"_id": 0}))
        assert updated["status"] == "pagado" and updated["enrolled"] is True
        enr = _run(db.enrollments.find_one({"user_id": user["id"], "course_id": "test-c1"}))
        assert enr is not None
        _run(db.users.delete_many({"email": email}))
        _run(db.enrollments.delete_many({"user_id": user["id"]}))
        _run(db.payments.delete_many({"id": pay["id"]}))

    def test_send_link_with_fake_keys_errors(self, db, admin_hdr):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import new_id, now_iso
        email = "delivered+sendlink@resend.dev"
        _run(db.users.delete_many({"email": email}))
        user = {"id": new_id(), "email": email, "nombre": "TEST_SL", "apellidos": "User",
                "role": "estudiante", "active": True, "created_at": now_iso()}
        _run(db.users.insert_one(dict(user)))
        before = _run(db.payments.count_documents({"email": email}))
        r = requests.post(f"{API}/payments/send-link", headers=admin_hdr,
                          json={"user_id": user["id"], "course_id": "test-c1"})
        assert r.status_code == 400, r.text
        # no orphan
        assert _run(db.payments.count_documents({"email": email})) == before
        _run(db.users.delete_many({"email": email}))


# ---------- Logged-in user visiting / ----------
# Handled on frontend; backend test skipped.
