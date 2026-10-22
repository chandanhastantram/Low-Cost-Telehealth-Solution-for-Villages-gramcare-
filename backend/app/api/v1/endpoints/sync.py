"""
GramCare – Delta synchronisation endpoints

POST /api/v1/sync/upload  – client pushes outbox entries
GET  /api/v1/sync/pull    – client pulls changes since checkpoint
GET  /api/v1/sync/status  – check current server version

Conflict rules (from paper §8.2):
  - Append-only data (encounters, prescriptions): merged by union — inserts
    are always accepted; updates are refused (corrections are new entries)
  - Demographic fields (patient_profiles): last-writer-wins, conflict logged
    in audit and reported back with the overwritten server copy
  - Appointments: server-authoritative — a stale update or a booking for a
    taken slot is rejected and the client gets alternative slots

Every entry is validated with the same schemas and access rules as the
REST endpoints, and processed in its own savepoint so one bad entry never
blocks the rest of the batch.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.encounters import build_encounter, create_prescription
from app.core.access import (
    can_access_appointment,
    get_own_patient_profile,
    load_encounter_or_404,
    load_patient_or_404,
)
from app.core.config import settings
from app.core.deps import CurrentUser, get_db
from app.models.models import (
    Appointment,
    AppointmentStatus,
    AuditLog,
    AuditAction,
    DoctorProfile,
    PatientProfile,
    SyncChangeLog,
    User,
    UserRole,
)
from app.schemas.schemas import (
    AppointmentCreate,
    AppointmentUpdate,
    EncounterCreate,
    OutboxEntry,
    PatientProfileCreate,
    PatientProfileUpdate,
    PrescriptionCreate,
    SyncConflict,
    SyncEntryResult,
    SyncPullResponse,
    SyncUploadRequest,
    SyncUploadResponse,
)
from app.services.scheduling import alternative_slots, is_slot_free
from app.utils.audit import log_action
from app.utils.sync import SYNCED_MODELS, get_current_version, record_change, serialize_record

router = APIRouter(prefix="/sync", tags=["Sync"])

APPEND_ONLY_TABLES = {"encounters", "prescriptions"}
LAST_WRITER_WINS_TABLES = {"patient_profiles"}
SERVER_AUTHORITATIVE_TABLES = {"appointments"}

_STAFF = {UserRole.chw, UserRole.admin}
WRITE_ROLES = {
    "patient_profiles": _STAFF,
    "encounters": {UserRole.chw, UserRole.doctor, UserRole.admin},
    "prescriptions": {UserRole.doctor, UserRole.admin},
    "appointments": _STAFF,
}


class SyncPrescriptionCreate(PrescriptionCreate):
    encounter_id: uuid.UUID


class Rejected(Exception):
    def __init__(self, reason: str, conflict: Optional[SyncConflict] = None):
        super().__init__(reason)
        self.reason = reason
        self.conflict = conflict


@dataclass
class Outcome:
    status: str = "accepted"
    reason: Optional[str] = None
    server_version: Optional[int] = None
    conflict: Optional[SyncConflict] = None


def _validate(schema: type[BaseModel], payload: dict) -> BaseModel:
    try:
        return schema.model_validate(payload)
    except ValidationError as e:
        first = e.errors()[0]
        raise Rejected(f"invalid payload: {'.'.join(map(str, first['loc']))}: {first['msg']}")


async def _guard(coro):
    """Turn REST-style 404/403 from the shared loaders into a rejection."""
    try:
        return await coro
    except HTTPException as e:
        raise Rejected(str(e.detail))


def _conflict(table: str, record_id: uuid.UUID, obj, resolution: str, alternatives=()) -> SyncConflict:
    return SyncConflict(
        record_id=str(record_id),
        table_name=table,
        server_payload=serialize_record(obj) if obj is not None else {},
        resolution=resolution,
        alternative_slots=list(alternatives),
    )


# ── Inserts ───────────────────────────────────────────────────────────────────

async def _insert(entry: OutboxEntry, record_id: uuid.UUID, user: User, db: AsyncSession):
    table = entry.table_name
    payload = {k: v for k, v in entry.payload.items() if k != "id"}

    if table == "patient_profiles":
        body = _validate(PatientProfileCreate, payload)
        target = await db.get(User, body.user_id)
        if not target or target.role != UserRole.patient:
            raise Rejected("user not found or not a patient account")
        existing = (
            await db.execute(select(PatientProfile).where(PatientProfile.user_id == body.user_id))
        ).scalar_one_or_none()
        if existing:
            raise Rejected(
                "patient already registered",
                _conflict(table, existing.id, existing, "rejected"),
            )
        data = body.model_dump(exclude={"idempotency_key"})
        if user.role == UserRole.chw:
            data["facility_id"] = user.facility_id
        obj = PatientProfile(id=record_id, **data)
        if obj.consent_recorded:
            obj.consent_timestamp = datetime.now(timezone.utc)

    elif table == "encounters":
        body = _validate(EncounterCreate, payload)
        await _guard(load_patient_or_404(db, user, body.patient_id))
        obj = build_encounter(body, user)
        obj.id = record_id
        obj.idempotency_key = entry.idempotency_key

    elif table == "prescriptions":
        body = _validate(SyncPrescriptionCreate, payload)
        body.idempotency_key = entry.idempotency_key
        encounter = await _guard(load_encounter_or_404(db, user, body.encounter_id))
        rx = await create_prescription(db, encounter, body, user)
        return rx  # create_prescription already recorded the change

    elif table == "appointments":
        body = _validate(AppointmentCreate, payload)
        patient = await _guard(load_patient_or_404(db, user, body.patient_id))
        if not await db.get(DoctorProfile, body.doctor_id):
            raise Rejected("doctor not found")
        if not await is_slot_free(db, body.doctor_id, body.scheduled_at, body.duration_minutes):
            raise Rejected(
                "slot already booked",
                _conflict(table, record_id, None, "rejected",
                          await alternative_slots(db, body.doctor_id, body.scheduled_at)),
            )
        data = body.model_dump(exclude={"idempotency_key"})
        data["facility_id"] = data["facility_id"] or patient.facility_id
        obj = Appointment(
            id=record_id,
            **data,
            chw_id=user.id if user.role == UserRole.chw else None,
            status=AppointmentStatus.confirmed,
            idempotency_key=entry.idempotency_key,
            call_room_name=f"gramcare-{record_id}",
        )
    else:  # pragma: no cover — guarded by WRITE_ROLES
        raise Rejected(f"unknown table {table}")

    db.add(obj)
    await record_change(db, table, obj, "insert", user.id, entry.idempotency_key)
    return obj


# ── Updates ───────────────────────────────────────────────────────────────────

async def _update(entry: OutboxEntry, existing, user: User, db: AsyncSession) -> Optional[SyncConflict]:
    table = entry.table_name
    stale = (existing.server_version or 0) > entry.local_version

    if table == "patient_profiles":
        await _guard(load_patient_or_404(db, user, existing.id))
        body = _validate(PatientProfileUpdate, entry.payload)
        conflict = None
        if stale:
            conflict = _conflict(table, existing.id, existing, "last_writer_wins")
            db.add(AuditLog(
                actor_id=user.id,
                action=AuditAction.update,
                resource_type=table,
                resource_id=str(existing.id),
                details={
                    "conflict": "last_writer_wins",
                    "local_version": entry.local_version,
                    "server_version": existing.server_version,
                    "overwritten": conflict.server_payload,
                },
            ))
        for name, value in body.model_dump(exclude_unset=True, exclude={"idempotency_key"}).items():
            setattr(existing, name, value)
        await record_change(db, table, existing, "update", user.id, entry.idempotency_key)
        return conflict

    if table == "appointments":
        if not await can_access_appointment(db, user, existing):
            raise Rejected("Not authorized for this appointment.")
        body = _validate(AppointmentUpdate, entry.payload)
        changes = body.model_dump(exclude_none=True, exclude={"idempotency_key"})
        new_time = changes.get("scheduled_at")
        if stale:
            alts = await alternative_slots(db, existing.doctor_id, new_time) if new_time else []
            raise Rejected("appointment changed on server", _conflict(table, existing.id, existing, "rejected", alts))
        if new_time and not await is_slot_free(
            db, existing.doctor_id, new_time, existing.duration_minutes, exclude_id=existing.id
        ):
            raise Rejected(
                "slot already booked",
                _conflict(table, existing.id, existing, "rejected",
                          await alternative_slots(db, existing.doctor_id, new_time)),
            )
        for name, value in changes.items():
            setattr(existing, name, value)
        await record_change(db, table, existing, "update", user.id, entry.idempotency_key)
        return None

    raise Rejected("append-only record: send a new entry instead of an update")


async def _handle_entry(entry: OutboxEntry, user: User, db: AsyncSession) -> Outcome:
    table = entry.table_name
    if table not in SYNCED_MODELS:
        return Outcome("rejected", f"unknown table {table}")
    if user.role not in WRITE_ROLES[table]:
        return Outcome("rejected", f"role '{user.role.value}' may not write {table}")
    try:
        record_id = uuid.UUID(entry.record_id)
    except ValueError:
        return Outcome("rejected", "record_id must be a UUID")

    # Idempotency: this exact outbox entry was already applied.
    done = (
        await db.execute(
            select(SyncChangeLog).where(SyncChangeLog.idempotency_key == entry.idempotency_key)
        )
    ).scalars().first()
    if done:
        return Outcome("accepted", "duplicate", done.version)

    model = SYNCED_MODELS[table]
    existing = await db.get(model, record_id)

    try:
        async with db.begin_nested():
            if entry.operation == "insert":
                if existing:
                    return Outcome("accepted", "already exists", existing.server_version)
                obj = await _insert(entry, record_id, user, db)
                await db.flush()
                return Outcome("accepted", server_version=obj.server_version)
            if entry.operation == "update":
                if not existing:
                    return Outcome("rejected", "record not found")
                conflict = await _update(entry, existing, user, db)
                await db.flush()
                return Outcome(
                    "conflict" if conflict else "accepted",
                    "last_writer_wins" if conflict else None,
                    existing.server_version,
                    conflict,
                )
            raise Rejected(
                "deletes are not synced; cancel appointments via a status update"
            )
    except Rejected as r:
        return Outcome("conflict" if r.conflict else "rejected", r.reason, conflict=r.conflict)


@router.post("/upload", response_model=SyncUploadResponse)
async def sync_upload(
    body: SyncUploadRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Client uploads batched outbox entries (at most SYNC_MAX_BATCH_SIZE are
    processed; the client re-sends the rest). Each entry gets a result.
    """
    results: list[SyncEntryResult] = []
    conflicts: list[SyncConflict] = []

    for entry in body.entries[:settings.SYNC_MAX_BATCH_SIZE]:
        outcome = await _handle_entry(entry, current_user, db)
        results.append(SyncEntryResult(
            idempotency_key=entry.idempotency_key,
            status=outcome.status,
            reason=outcome.reason,
            server_version=outcome.server_version,
        ))
        if outcome.conflict:
            conflicts.append(outcome.conflict)

    # A last-writer-wins conflict is still applied (it carries a server_version);
    # a rejected conflict is not.
    accepted = sum(
        r.status == "accepted" or (r.status == "conflict" and r.server_version is not None)
        for r in results
    )
    await log_action(
        db, current_user.id, "sync", "sync_upload", body.client_id,
        {"accepted": accepted, "rejected": len(results) - accepted, "conflicts": len(conflicts)},
    )
    await db.commit()

    return SyncUploadResponse(
        accepted=accepted,
        rejected=len(results) - accepted,
        conflicts=conflicts,
        results=results,
        new_checkpoint=await get_current_version(db),
    )


@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(
    current_user: CurrentUser,
    since: int = Query(0, description="Last checkpoint version the client has"),
    facility_id: Optional[uuid.UUID] = Query(None, description="Admin/doctor only: narrow to one facility"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Pull changes since the given checkpoint, scoped to what the caller may
    see: patients get only their own records, CHWs their facility, doctors
    and admins everything (optionally narrowed by facility_id).
    """
    query = select(SyncChangeLog).where(SyncChangeLog.version > since)

    if current_user.role == UserRole.patient:
        profile = await get_own_patient_profile(db, current_user)
        query = query.where(SyncChangeLog.patient_id == (profile.id if profile else None))
    elif current_user.role == UserRole.chw:
        query = query.where(SyncChangeLog.facility_id == current_user.facility_id)
    elif facility_id:
        query = query.where(SyncChangeLog.facility_id == facility_id)

    query = query.order_by(SyncChangeLog.version.asc()).limit(limit + 1)
    rows = (await db.execute(query)).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    changes = [
        {
            "version": r.version,
            "table_name": r.table_name,
            "record_id": str(r.record_id),
            "operation": r.operation,
            "payload": r.payload,
            "changed_at": r.changed_at.isoformat(),
        }
        for r in rows
    ]

    return SyncPullResponse(
        changes=changes,
        new_checkpoint=rows[-1].version if rows else since,
        has_more=has_more,
    )


@router.get("/status")
async def sync_status(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return current server version and sync health."""
    version = await get_current_version(db)
    return {
        "server_version": version,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "client_id_hint": str(current_user.id),
    }
