"""
GramCare – Encounter (health record) endpoints
POST  /api/v1/encounters                        – create encounter
GET   /api/v1/encounters/{id}                   – get encounter
POST  /api/v1/encounters/{id}/prescriptions     – write prescription (doctor)
GET   /api/v1/encounters/{id}/prescriptions     – list prescriptions

Encounters and prescriptions are append-only: corrections are new entries.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.triage import run_triage
from app.core.access import load_encounter_or_404, load_patient_or_404
from app.core.deps import CHWOrAbove, CurrentUser, get_db, require_roles
from app.models.models import (
    Encounter,
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
from app.utils.sync import record_change

router = APIRouter(prefix="/encounters", tags=["Encounters"])


def build_encounter(body: EncounterCreate, current_user) -> Encounter:
    """Shared by REST and /sync/upload so both store the same shape."""
    enc_data = body.model_dump(exclude={"vitals", "idempotency_key"})
    if body.vitals:
        enc_data.update(body.vitals.model_dump(exclude_none=True))
    if not body.triage_flags and (body.symptoms_json or body.vitals):
        enc_data["triage_flags"] = run_triage(body.symptoms_json, body.vitals).model_dump()
    return Encounter(
        **enc_data,
        chw_id=current_user.id if current_user.role == UserRole.chw else None,
        doctor_id=current_user.id if current_user.role == UserRole.doctor else None,
        idempotency_key=body.idempotency_key,
    )


@router.post("", response_model=EncounterResponse, status_code=status.HTTP_201_CREATED)
async def create_encounter(
    body: EncounterCreate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """Create a new clinical encounter. Red-flag triage runs automatically."""
    if body.idempotency_key:
        result = await db.execute(
            select(Encounter).where(Encounter.idempotency_key == body.idempotency_key)
        )
        if (existing := result.scalar_one_or_none()):
            return existing

    await load_patient_or_404(db, current_user, body.patient_id)

    encounter = build_encounter(body, current_user)
    encounter.id = uuid.uuid4()
    db.add(encounter)
    await record_change(db, "encounters", encounter, "insert", current_user.id, body.idempotency_key)
    await log_action(db, current_user.id, "create", "encounter", str(encounter.id))
    await db.commit()
    await db.refresh(encounter)
    return encounter


@router.get("/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    encounter = await load_encounter_or_404(db, current_user, encounter_id)
    await log_action(db, current_user.id, "read", "encounter", str(encounter_id))
    return encounter


# ── Prescriptions ─────────────────────────────────────────────────────────────

def build_prescription(encounter_id: uuid.UUID, body: PrescriptionCreate, current_user) -> Prescription:
    return Prescription(
        encounter_id=encounter_id,
        doctor_id=current_user.id,
        medications=[m.model_dump() for m in body.medications],
        advice=body.advice,
        follow_up_date=body.follow_up_date,
        referral_facility=body.referral_facility,
        idempotency_key=body.idempotency_key,
    )


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
    if body.idempotency_key:
        result = await db.execute(
            select(Prescription).where(Prescription.idempotency_key == body.idempotency_key)
        )
        if (existing := result.scalar_one_or_none()):
            return existing

    encounter = await load_encounter_or_404(db, current_user, encounter_id)
    rx = await create_prescription(db, encounter, body, current_user)
    await db.commit()
    await db.refresh(rx)
    return rx


async def create_prescription(db: AsyncSession, encounter: Encounter, body: PrescriptionCreate, current_user) -> Prescription:
    """Adds the prescription (and claims the encounter for the doctor). Caller commits."""
    rx = build_prescription(encounter.id, body, current_user)
    rx.id = uuid.uuid4()
    db.add(rx)
    await record_change(db, "prescriptions", rx, "insert", current_user.id, body.idempotency_key)
    if current_user.role == UserRole.doctor and encounter.doctor_id is None:
        encounter.doctor_id = current_user.id
        await record_change(db, "encounters", encounter, "update", current_user.id)
    await log_action(db, current_user.id, "create", "prescription", str(rx.id))
    return rx


@router.get("/{encounter_id}/prescriptions", response_model=list[PrescriptionResponse])
async def list_prescriptions(
    encounter_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await load_encounter_or_404(db, current_user, encounter_id)
    result = await db.execute(
        select(Prescription)
        .where(Prescription.encounter_id == encounter_id)
        .order_by(Prescription.issued_at.desc())
    )
    return result.scalars().all()
