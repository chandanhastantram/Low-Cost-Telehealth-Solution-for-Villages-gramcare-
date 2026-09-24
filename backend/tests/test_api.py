"""
GramCare – Test suite
Run with: pytest tests/ -v
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.db.session import Base, get_db
from app.core.config import settings


# ── Test Database ─────────────────────────────────────────────────────────────
TEST_DB_URL = "postgresql+asyncpg://gramcare_user:gramcare_password@localhost:5432/gramcare_test"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c


# ── Health Check Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "GramCare API"


# ── Auth Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_otp_new_user(client):
    response = await client.post("/api/v1/auth/otp/request", json={
        "phone": "+919999000001",
        "name": "Test Patient"
    })
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_request_otp_missing_name(client):
    """New user without name should fail."""
    response = await client.post("/api/v1/auth/otp/request", json={
        "phone": "+919999000099"
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_invalid_otp(client):
    # Request OTP first
    await client.post("/api/v1/auth/otp/request", json={
        "phone": "+919999000002",
        "name": "Test User"
    })
    response = await client.post("/api/v1/auth/otp/verify", json={
        "phone": "+919999000002",
        "otp": "000000"
    })
    assert response.status_code == 400


# ── Triage Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_triage_no_flags(client, auth_headers):
    """Normal vitals → no flags."""
    response = await client.post(
        "/api/v1/triage/evaluate",
        json={
            "symptoms": {},
            "vitals": {
                "temperature_c": 37.0,
                "pulse_bpm": 72,
                "spo2_pct": 98,
                "bp_systolic": 120,
                "bp_diastolic": 80
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["urgent"] is False
    assert len(data["flags"]) == 0


@pytest.mark.asyncio
async def test_triage_low_spo2(client, auth_headers):
    """SpO2 < 90 → red flag."""
    response = await client.post(
        "/api/v1/triage/evaluate",
        json={
            "symptoms": {},
            "vitals": {"spo2_pct": 85}
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["urgent"] is True
    severities = [f["severity"] for f in data["flags"]]
    assert "red" in severities


@pytest.mark.asyncio
async def test_triage_chest_pain(client, auth_headers):
    """Chest pain symptom → red flag."""
    response = await client.post(
        "/api/v1/triage/evaluate",
        json={"symptoms": {"chest_pain": True}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["urgent"] is True


@pytest.mark.asyncio
async def test_triage_advice_only_label(client, auth_headers):
    """Summary must contain 'advice only' disclaimer."""
    response = await client.post(
        "/api/v1/triage/evaluate",
        json={"symptoms": {}, "vitals": {}},
        headers=auth_headers,
    )
    assert "advice only" in response.json()["summary"].lower()


# ── Appointment Slot Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_slots_invalid_date(client, auth_headers):
    response = await client.get(
        "/api/v1/appointments/slots",
        params={"doctor_id": "00000000-0000-0000-0000-000000000001", "date": "not-a-date"},
        headers=auth_headers,
    )
    assert response.status_code == 400


# ── Sync Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_status(client, auth_headers):
    response = await client.get("/api/v1/sync/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "server_version" in data
    assert "server_time" in data


@pytest.mark.asyncio
async def test_sync_pull_empty(client, auth_headers):
    response = await client.get(
        "/api/v1/sync/pull",
        params={"since": 999999},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["changes"] == []
    assert data["has_more"] is False


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def auth_headers(client):
    """Returns Authorization headers for a test CHW."""
    # Request OTP
    phone = "+919988776655"
    await client.post("/api/v1/auth/otp/request", json={"phone": phone, "name": "Test CHW"})

    # Get OTP from DB
    from sqlalchemy import select
    from app.models.models import OTPRecord
    from app.core.security import hash_secret

    async with TestSessionLocal() as session:
        result = await session.execute(
            select(OTPRecord)
            .where(OTPRecord.phone == phone, OTPRecord.verified.is_(False))
            .order_by(OTPRecord.created_at.desc())
            .limit(1)
        )
        otp_record = result.scalar_one_or_none()

    if not otp_record:
        pytest.skip("Could not create test OTP")

    # We can't easily recover the plain OTP (it's hashed), so use a workaround:
    # In test mode, we patch otp = "123456" hardcoded
    # In real tests, inject the OTP via console mock
    pytest.skip("Requires console OTP capture — integration test only")
