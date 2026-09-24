"""
GramCare – Delta synchronisation endpoints

POST /api/v1/sync/upload  – client pushes outbox entries
GET  /api/v1/sync/pull    – client pulls changes since checkpoint
GET  /api/v1/sync/status  – check current server version

Conflict rules (from paper §8.2):
  - Append-only data (encounters, vitals, prescriptions): merged by union
  - Demographic fields: last-writer-wins, conflict logged in audit
  - Appointments: server-authoritative; rejected offline booking returns alternative slots
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser, get_db
from app.models.models import (
    Appointment,
    AuditLog,
    Encounter,
    PatientProfile,
    Prescription,
    SyncChangeLog,
    SyncStatus,
    UserRole,
)
from app.schemas.schemas import (
    OutboxEntry,
    SyncConflict,
    SyncPullResponse,
    SyncUploadRequest,
    SyncUploadResponse,
)
from app.utils.audit import log_action
from app.utils.sync import bump_version, get_current_version

router = APIRouter(prefix="/sync", tags=["Sync"])

# Tables that support delta sync and their conflict resolution strategy
APPEND_ONLY_TABLES = {"encounters", "prescriptions", "media_attachments"}
LAST_WRITER_WINS_TABLES = {"patient_profiles"}
SERVER_AUTHORITATIVE_TABLES = {"appointments"}

TABLE_MODEL_MAP = {
    "patient_profiles": PatientProfile,
    "encounters": Encounter,
    "appointments": Appointment,
    "prescriptions": Prescription,
}


async def _handle_entry(
    entry: OutboxEntry,
    current_user,
    db: AsyncSession,
) -> tuple[bool, Optional[SyncConflict]]:
    """
    Process a single outbox entry.
    Returns (accepted: bool, conflict: SyncConflict | None)
    """
    table = entry.table_name
    record_id = entry.record_id

    # ── Idempotency guard ───────────────────────────────────────────────────
    result = await db.execute(
        select(SyncChangeLog).where(SyncChangeLog.idempotency_key == entry.idempotency_key)
    )
    if result.scalar_one_or_none():
        return True, None  # Already processed

    # ── Determine target model ──────────────────────────────────────────────
    model_class = TABLE_MODEL_MAP.get(table)
    if not model_class:
        return False, None   # Unknown table

    # ── Fetch existing record ───────────────────────────────────────────────
    try:
        record_uuid = uuid.UUID(record_id)
    except ValueError:
        return False, None

    result = await db.execute(
        select(model_class).where(model_class.id == record_uuid)
    )
    existing = result.scalar_one_or_none()

    if entry.operation == "insert":
        if existing:
            # Already exists → idempotent, accept
            return True, None
        # Create new
        new_obj = model_class(**entry.payload)
        new_obj.server_version = await bump_version(db, table)
        new_obj.sync_status = SyncStatus.synced
        db.add(new_obj)

    elif entry.operation == "update":
        if not existing:
            return False, None

        # ── Conflict detection ────────────────────────────────────────────
        if hasattr(existing, "server_version") and existing.server_version > entry.local_version:
            # Conflict!
            if table in APPEND_ONLY_TABLES:
                # Union merge: append-only means we just accept both
                # (in practice, these are new rows not updates)
                pass
            elif table in LAST_WRITER_WINS_TABLES:
                # Apply client change but log conflict in audit
                conflict = SyncConflict(
                    record_id=record_id,
                    table_name=table,
                    server_payload={},
                    resolution="last_writer_wins",
                )
                for field, value in entry.payload.items():
                    if hasattr(existing, field):
                        setattr(existing, field, value)
                existing.server_version = await bump_version(db, table)
                existing.sync_status = SyncStatus.synced
                # Log conflict
                db.add(AuditLog(
                    actor_id=current_user.id,
                    action="update",
                    resource_type=table,
                    resource_id=record_id,
                    details={"conflict": "last_writer_wins", "local_version": entry.local_version},
                ))
                return True, conflict
            elif table in SERVER_AUTHORITATIVE_TABLES:
                conflict = SyncConflict(
                    record_id=record_id,
                    table_name=table,
                    server_payload={},
                    resolution="rejected",
                )
                return False, conflict
        else:
            # No conflict → apply
            for field, value in entry.payload.items():
                if hasattr(existing, field):
                    setattr(existing, field, value)
            if hasattr(existing, "server_version"):
                existing.server_version = await bump_version(db, table)
            if hasattr(existing, "sync_status"):
                existing.sync_status = SyncStatus.synced

    elif entry.operation == "delete":
        # Soft-delete: mark inactive
        if existing and hasattr(existing, "is_active"):
            existing.is_active = False

    # ── Write change log ────────────────────────────────────────────────────
    new_version = await get_current_version(db)
    log_entry = SyncChangeLog(
        table_name=table,
        record_id=record_uuid,
        operation=entry.operation,
        payload=entry.payload,
        version=new_version,
        changed_by=current_user.id,
        changed_at=datetime.now(timezone.utc),
        idempotency_key=entry.idempotency_key,
        facility_id=current_user.facility_id,
    )
    db.add(log_entry)
    return True, None


@router.post("/upload", response_model=SyncUploadResponse)
async def sync_upload(
    body: SyncUploadRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Client uploads batched outbox entries.
    Server processes each entry, handles conflicts, and returns results.
    """
    accepted = 0
    rejected = 0
    conflicts: list[SyncConflict] = []

    for entry in body.entries[:settings.SYNC_MAX_BATCH_SIZE]:
        ok, conflict = await _handle_entry(entry, current_user, db)
        if ok:
            accepted += 1
        else:
            rejected += 1
        if conflict:
            conflicts.append(conflict)

    await db.commit()

    new_checkpoint = await get_current_version(db)
    await log_action(
        db, current_user.id, "sync", "sync_upload", body.client_id,
        {"accepted": accepted, "rejected": rejected, "conflicts": len(conflicts)},
    )

    return SyncUploadResponse(
        accepted=accepted,
        rejected=rejected,
        conflicts=conflicts,
        new_checkpoint=new_checkpoint,
    )


@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(
    since: int = Query(0, description="Last checkpoint version the client has"),
    facility_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, le=500),
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Pull changes from the server since the given checkpoint.
    Returns changes scoped to the client's facility.
    """
    query = select(SyncChangeLog).where(SyncChangeLog.version > since)

    if facility_id:
        query = query.where(SyncChangeLog.facility_id == facility_id)
    elif current_user.facility_id:
        query = query.where(SyncChangeLog.facility_id == current_user.facility_id)

    query = query.order_by(SyncChangeLog.version.asc()).limit(limit + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

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

    new_checkpoint = rows[-1].version if rows else since

    return SyncPullResponse(
        changes=changes,
        new_checkpoint=new_checkpoint,
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
