"""
GramCare – Test suite
Run with: pytest tests/ -v
"""

import pytest

pytestmark = pytest.mark.asyncio


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
