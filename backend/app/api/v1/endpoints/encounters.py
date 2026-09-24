"""
GramCare – Encounter (health record) endpoints
POST  /api/v1/encounters         – create encounter
GET   /api/v1/encounters/{id}    – get encounter
PATCH /api/v1/encounters/{id}    – update (add prescription / close)
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CHWOrAbove, CurrentUser, get_db, require_roles
from app.models.models import (
    Encounter,
    PatientProfile,
    Prescription,
    UserRole,
)
from app.schemas.schemas import (
    EncounterCreate,
    EncounterResponse,
    PrescriptionCreate,
    PrescriptionResponse,
)
from app.utils.audit import log_action
from app.utils.sync import bump_version

router = APIRouter(prefix="/encounters", tags=["Encounters"])


@router.post("", response_model=EncounterResponse, status_code=status.HTTP_201_CREATED)
async def create_encounter(
    body: EncounterCreate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """Create a new clinical encounter / health record entry."""
    # Idempotency check
    if body.idempotency_key:
        result = await db.execute(
            select(Encounter).where(Encounter.idempotency_key == body.idempotency_key)
        )
        if result.scalar_one_or_none():
            return result.scalar_one_or_none()

    enc_data = body.model_dump(exclude={"vitals", "idempotency_key"})
    if body.vitals:
        enc_data.update(body.vitals.model_dump(exclude_none=True))

    encounter = Encounter(
        **enc_data,
        chw_id=current_user.id if current_user.role == UserRole.chw else None,
        idempotency_key=body.idempotency_key,
    )
    encounter.server_version = await bump_version(db, "encounters")
    db.add(encounter)
    await db.commit()
    await db.refresh(encounter)
    await log_action(db, current_user.id, "create", "encounter", str(encounter.id))
    return encounter


@router.get("/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Encounter)
        .where(Encounter.id == encounter_id)
        .options(selectinload(Encounter.prescriptions))
    )
    encounter = result.scalar_one_or_none()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found.")
    await log_action(db, current_user.id, "read", "encounter", str(encounter_id))
    return encounter


# ── Prescriptions ─────────────────────────────────────────────────────────────

@router.post(
    "/{encounter_id}/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_prescription(
    encounter_id: uuid.UUID,
    body: PrescriptionCreate,
    current_user=Depends(require_roles(UserRole.doctor, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Only doctors/admins can write prescriptions."""
    # Idempotency
    if body.idempotency_key:
        result = await db.execute(
            select(Prescription).where(Prescription.idempotency_key == body.idempotency_key)
        )
        if (existing := result.scalar_one_or_none()):
            return existing

    rx = Prescription(
        encounter_id=encounter_id,
        doctor_id=current_user.id,
        medications=[m.model_dump() for m in body.medications],
        advice=body.advice,
        follow_up_date=body.follow_up_date,
        referral_facility=body.referral_facility,
        idempotency_key=body.idempotency_key,
    )
    rx.server_version = await bump_version(db, "prescriptions")
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    await log_action(db, current_user.id, "create", "prescription", str(rx.id))
    return rx


@router.get("/{encounter_id}/prescriptions", response_model=list[PrescriptionResponse])
async def list_prescriptions(
    encounter_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Prescription).where(Prescription.encounter_id == encounter_id)
    )
    return result.scalars().all()
