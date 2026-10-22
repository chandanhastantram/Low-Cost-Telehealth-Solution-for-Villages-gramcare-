"""
GramCare – Sync version management utilities

Every write to a synced table (REST endpoint or /sync/upload) goes through
`record_change`, which assigns the record a fresh server_version and appends
a matching SyncChangeLog row. That keeps one invariant the pull endpoint
relies on: a client holding checkpoint N sees every change with version > N,
no matter which path produced it.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Appointment,
    Encounter,
    PatientProfile,
    Prescription,
    SyncChangeLog,
    SyncStatus,
)

SYNCED_MODELS = {
    "patient_profiles": PatientProfile,
    "encounters": Encounter,
    "appointments": Appointment,
    "prescriptions": Prescription,
}

# Never shipped to devices.
_PRIVATE_FIELDS = {"idempotency_key", "client_id", "sync_status"}


async def get_current_version(db: AsyncSession) -> int:
    """Return the highest version number in the change log."""
    result = await db.execute(select(func.max(SyncChangeLog.version)))
    val = result.scalar()
    return val or 0


async def bump_version(db: AsyncSession, table_name: str = "") -> int:
    """
    Next monotonically increasing version. PostgreSQL uses a sequence (safe
    under concurrency); other dialects (SQLite in tests) fall back to
    max(change_log.version) + 1, which is fine for a single writer.
    """
    if db.bind.dialect.name == "postgresql":
        result = await db.execute(text("SELECT nextval('sync_version_seq')"))
        return result.scalar()
    await db.flush()
    return await get_current_version(db) + 1


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


def serialize_record(obj) -> dict:
    """Column values already loaded on `obj` (never triggers a lazy load)."""
    state = inspect(obj)
    loaded = state.dict
    return {
        attr.key: _json_safe(loaded[attr.key])
        for attr in state.mapper.column_attrs
        if attr.key in loaded and attr.key not in _PRIVATE_FIELDS
    }


async def _scope_for(db: AsyncSession, table_name: str, obj) -> tuple[Optional[uuid.UUID], Optional[uuid.UUID]]:
    """(patient_id, facility_id) a change belongs to, for pull scoping."""
    if table_name == "patient_profiles":
        return obj.id, obj.facility_id
    if table_name == "prescriptions":
        encounter = await db.get(Encounter, obj.encounter_id)
        patient_id = encounter.patient_id if encounter else None
    else:
        patient_id = obj.patient_id
    patient = await db.get(PatientProfile, patient_id) if patient_id else None
    return patient_id, patient.facility_id if patient else None


async def record_change(
    db: AsyncSession,
    table_name: str,
    obj,
    operation: str,
    actor_id: Optional[uuid.UUID],
    idempotency_key: Optional[str] = None,
) -> int:
    """Bump obj.server_version and append the change-log row. Caller commits."""
    if obj.id is None:
        obj.id = uuid.uuid4()
    version = await bump_version(db, table_name)
    obj.server_version = version
    if hasattr(obj, "sync_status"):
        obj.sync_status = SyncStatus.synced
    patient_id, facility_id = await _scope_for(db, table_name, obj)
    db.add(SyncChangeLog(
        table_name=table_name,
        record_id=obj.id,
        operation=operation,
        payload=serialize_record(obj),
        version=version,
        changed_by=actor_id,
        changed_at=datetime.now().astimezone(),
        idempotency_key=idempotency_key,
        facility_id=facility_id,
        patient_id=patient_id,
    ))
    return version
