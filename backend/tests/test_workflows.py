"""
End-to-end workflows: access control, booking, records, offline sync,
store-and-forward and the offline PIN. Uses the `world` fixture (conftest).
"""

import uuid
from datetime import datetime, timedelta, timezone


API = "/api/v1"


def tomorrow_at(hour: int, minute: int = 0) -> str:
    d = datetime.now(timezone.utc).date() + timedelta(days=1)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc).isoformat()


async def make_encounter(client, w, headers=None, **extra):
    body = {
        "patient_id": str(w.p1.id),
        "encounter_date": datetime.now(timezone.utc).isoformat(),
        "chief_complaint": "fever",
        **extra,
    }
    r = await client.post(f"{API}/encounters", json=body, headers=headers or w.chw)
    assert r.status_code == 201, r.text
    return r.json()


async def pull(client, headers, since=0):
    r = await client.get(f"{API}/sync/pull", params={"since": since}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def entry(table, payload, op="insert", record_id=None, local_version=0):
    return {
        "operation": op,
        "table_name": table,
        "record_id": str(record_id or uuid.uuid4()),
        "payload": payload,
        "local_version": local_version,
        "idempotency_key": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def upload(client, headers, *entries):
    r = await client.post(
        f"{API}/sync/upload", json={"client_id": "dev-1", "entries": list(entries)}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── Access control ────────────────────────────────────────────────────────────

async def test_patient_sees_only_own_records(client, world):
    w = world
    await make_encounter(client, w)
    me = await client.get(f"{API}/patients/me", headers=w.pat1)
    assert me.json()["id"] == str(w.p1.id)

    own = await client.get(f"{API}/patients/{w.p1.id}/records", headers=w.pat1)
    assert own.status_code == 200 and len(own.json()["encounters"]) == 1
    other = await client.get(f"{API}/patients/{w.p1.id}/records", headers=w.pat2)
    assert other.status_code == 403


async def test_chw_limited_to_own_facility(client, world):
    w = world
    assert (await client.get(f"{API}/patients/{w.p1.id}", headers=w.chw)).status_code == 200
    assert (await client.get(f"{API}/patients/{w.p1.id}", headers=w.chw_b)).status_code == 403
    listed = (await client.get(f"{API}/patients", headers=w.chw_b)).json()["items"]
    assert [p["id"] for p in listed] == [str(w.p2.id)]
    r = await client.post(
        f"{API}/encounters",
        json={"patient_id": str(w.p1.id), "encounter_date": datetime.now(timezone.utc).isoformat()},
        headers=w.chw_b,
    )
    assert r.status_code == 403


async def test_users_cannot_move_themselves_between_facilities(client, world):
    w = world
    r = await client.patch(f"{API}/users/me", json={"facility_id": str(w.fac_a.id)}, headers=w.chw_b)
    assert r.status_code == 200 and r.json()["facility_id"] == str(w.fac_b.id)
    bad = await client.patch(f"{API}/users/me", json={"language_code": "xx"}, headers=w.chw_b)
    assert bad.status_code == 422


# ── Appointments ──────────────────────────────────────────────────────────────

async def test_booking_conflict_offers_alternatives(client, world):
    w = world
    body = {
        "patient_id": str(w.p1.id),
        "doctor_id": str(w.doctor_profile.id),
        "scheduled_at": tomorrow_at(10),
    }
    first = await client.post(f"{API}/appointments", json=body, headers=w.chw)
    assert first.status_code == 201, first.text

    clash = await client.post(f"{API}/appointments", json={**body, "scheduled_at": tomorrow_at(10, 5)}, headers=w.chw)
    assert clash.status_code == 409
    alts = clash.json()["alternative_slots"]
    assert alts and tomorrow_at(10) not in alts

    day = tomorrow_at(0)[:10]
    slots = (await client.get(
        f"{API}/appointments/slots",
        params={"doctor_id": str(w.doctor_profile.id), "date": day},
        headers=w.chw,
    )).json()["available_slots"]
    assert tomorrow_at(10) not in slots and tomorrow_at(10, 15) in slots


async def test_appointment_visibility_and_patient_cancel(client, world):
    w = world
    appt = (await client.post(f"{API}/appointments", json={
        "patient_id": str(w.p1.id),
        "doctor_id": str(w.doctor_profile.id),
        "scheduled_at": tomorrow_at(11),
    }, headers=w.chw)).json()

    assert (await client.get(f"{API}/appointments/{appt['id']}", headers=w.pat2)).status_code == 403
    assert (await client.get(f"{API}/appointments/{appt['id']}", headers=w.doctor)).status_code == 200
    mine = (await client.get(f"{API}/appointments", headers=w.pat1)).json()
    assert mine["total"] == 1

    resched = await client.patch(f"{API}/appointments/{appt['id']}", json={"notes": "x"}, headers=w.pat1)
    assert resched.status_code == 403
    cancel = await client.patch(f"{API}/appointments/{appt['id']}", json={"status": "cancelled"}, headers=w.pat1)
    assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"


# ── Encounters & prescriptions ────────────────────────────────────────────────

async def test_encounter_idempotent_and_auto_triaged(client, world):
    w = world
    key = str(uuid.uuid4())
    first = await make_encounter(client, w, idempotency_key=key, vitals={"spo2_pct": 84})
    again = await make_encounter(client, w, idempotency_key=key)
    assert again["id"] == first["id"]
    assert first["triage_flags"]["urgent"] is True


async def test_only_doctors_prescribe_and_chw_device_receives_it(client, world):
    w = world
    enc = await make_encounter(client, w)
    rx = {"medications": [{"name": "Paracetamol", "dose": "500mg", "frequency": "TDS", "duration": "3d"}]}

    assert (await client.post(f"{API}/encounters/{enc['id']}/prescriptions", json=rx, headers=w.chw)).status_code == 403
    checkpoint = (await pull(client, w.chw))["new_checkpoint"]

    r = await client.post(f"{API}/encounters/{enc['id']}/prescriptions", json=rx, headers=w.doctor)
    assert r.status_code == 201, r.text

    changes = (await pull(client, w.chw, since=checkpoint))["changes"]
    tables = {c["table_name"] for c in changes}
    assert "prescriptions" in tables
    assert all(c["version"] > checkpoint for c in changes)
    # CHW in another facility never sees it.
    assert not (await pull(client, w.chw_b))["changes"]


# ── Offline sync ──────────────────────────────────────────────────────────────

async def test_sync_upload_is_validated_idempotent_and_scoped(client, world):
    w = world
    enc = entry("encounters", {
        "patient_id": str(w.p1.id),
        "encounter_date": datetime.now(timezone.utc).isoformat(),
        "chief_complaint": "cough",
        "symptoms_json": {"difficulty_breathing": True},
    })
    res = await upload(client, w.chw, enc)
    assert res["accepted"] == 1 and res["results"][0]["status"] == "accepted"

    again = await upload(client, w.chw, enc)
    assert again["results"][0]["reason"] == "duplicate"

    bad = await upload(
        client, w.chw,
        entry("encounters", {"patient_id": "nope"}),
        entry("encounters", {"patient_id": str(w.p2.id), "encounter_date": datetime.now(timezone.utc).isoformat()}),
        entry("prescriptions", {"encounter_id": enc["record_id"], "medications": []}),
        entry("encounters", {"chief_complaint": "edit"}, op="update", record_id=enc["record_id"]),
    )
    statuses = [r["status"] for r in bad["results"]]
    assert statuses == ["rejected"] * 4, bad["results"]
    assert "append-only" in bad["results"][3]["reason"]

    # Patient 1 pulls their own encounter (auto-triaged); patient 2 gets nothing.
    p1 = (await pull(client, w.pat1))["changes"]
    assert [c["record_id"] for c in p1] == [enc["record_id"]]
    assert p1[0]["payload"]["triage_flags"]["urgent"] is True
    assert (await pull(client, w.pat2))["changes"] == []


async def test_sync_patient_profile_last_writer_wins(client, world):
    w = world
    stale = entry("patient_profiles", {"allergies": "penicillin"}, op="update", record_id=w.p1.id)
    r = await client.patch(f"{API}/patients/{w.p1.id}", json={"blood_group": "O+"}, headers=w.chw)
    assert r.status_code == 200

    res = await upload(client, w.chw, stale)
    assert res["results"][0]["status"] == "conflict"
    conflict = res["conflicts"][0]
    assert conflict["resolution"] == "last_writer_wins"
    assert conflict["server_payload"]["blood_group"] == "O+"
    final = (await client.get(f"{API}/patients/{w.p1.id}", headers=w.chw)).json()
    assert final["allergies"] == "penicillin" and final["blood_group"] == "O+"


async def test_sync_offline_booking_rejected_with_alternatives(client, world):
    w = world
    booking = {
        "patient_id": str(w.p1.id),
        "doctor_id": str(w.doctor_profile.id),
        "scheduled_at": tomorrow_at(9),
    }
    assert (await client.post(f"{API}/appointments", json=booking, headers=w.chw)).status_code == 201

    res = await upload(client, w.chw, entry("appointments", booking))
    assert res["accepted"] == 0 and res["rejected"] == 1
    conflict = res["conflicts"][0]
    assert conflict["resolution"] == "rejected" and conflict["alternative_slots"]


# ── Store-and-forward ─────────────────────────────────────────────────────────

async def test_store_forward_round_trip(client, world):
    w = world
    enc = await make_encounter(client, w)
    bundle = await client.post(f"{API}/teleconsult/store-forward", json={
        "encounter_id": enc["id"], "patient_id": str(w.p1.id), "payload_json": {"note": "rash"},
    }, headers=w.chw)
    assert bundle.status_code == 201, bundle.text
    bid = bundle.json()["id"]

    queue = (await client.get(f"{API}/teleconsult/store-forward", headers=w.doctor)).json()
    assert [b["id"] for b in queue] == [bid]

    reply = await client.post(f"{API}/teleconsult/store-forward/{bid}/respond", json={
        "response_text": "Apply calamine",
        "prescription": {"medications": [{"name": "Calamine", "dose": "topical", "frequency": "BD", "duration": "5d"}]},
    }, headers=w.doctor)
    assert reply.status_code == 200, reply.text
    assert reply.json()["prescription_id"]

    mine = (await client.get(f"{API}/teleconsult/store-forward", headers=w.chw)).json()
    assert mine[0]["status"] == "replied" and mine[0]["doctor_response"] == "Apply calamine"
    twice = await client.post(f"{API}/teleconsult/store-forward/{bid}/respond", params={"response_text": "again"}, headers=w.doctor)
    assert twice.status_code == 409


# ── Offline PIN ───────────────────────────────────────────────────────────────

async def test_offline_pin_lifecycle_and_lockout(client, world):
    w = world
    assert (await client.put(f"{API}/users/me/pin", json={"pin": "12"}, headers=w.chw)).status_code == 422
    assert (await client.put(f"{API}/users/me/pin", json={"pin": "4321"}, headers=w.chw)).status_code == 200
    assert (await client.get(f"{API}/users/me", headers=w.chw)).json()["has_offline_pin"] is True

    ok = await client.post(f"{API}/users/me/pin/verify", json={"pin": "4321"}, headers=w.chw)
    assert ok.json()["valid"] is True

    for remaining in (4, 3, 2, 1, 0):
        r = await client.post(f"{API}/users/me/pin/verify", json={"pin": "0000"}, headers=w.chw)
        assert r.json() == {"valid": False, "attempts_remaining": remaining}
    locked = await client.post(f"{API}/users/me/pin/verify", json={"pin": "4321"}, headers=w.chw)
    assert locked.status_code == 429


async def test_deactivated_user_cannot_log_in(client, world, session_factory):
    w = world
    me = (await client.get(f"{API}/users/me", headers=w.pat2)).json()
    r = await client.patch(f"{API}/users/{me['id']}", json={"is_active": False}, headers=w.admin)
    assert r.status_code == 200
    assert (await client.get(f"{API}/users/me", headers=w.pat2)).status_code == 401
    await client.post(f"{API}/auth/otp/request", json={"phone": me["phone"]})
    v = await client.post(f"{API}/auth/otp/verify", json={"phone": me["phone"], "otp": client.sent_otps[me["phone"]]})
    assert v.status_code == 403
