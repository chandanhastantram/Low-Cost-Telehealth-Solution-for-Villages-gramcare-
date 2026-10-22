"""
GramCare – Patient endpoints
GET    /api/v1/patients              – list (CHW sees own facility)
POST   /api/v1/patients              – register patient
GET    /api/v1/patients/me           – own profile (patient role)
GET    /api/v1/patients/{id}         – get patient
PATCH  /api/v1/patients/{id}         – update patient
GET    /api/v1/patients/{id}/records – full health timeline
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.access import get_own_patient_profile, load_patient_or_404
from app.core.deps import CHWOrAbove, CurrentUser, get_db
from app.models.models import (
    Encounter,
    PatientProfile,
    User,
    UserRole,
)
from app.schemas.schemas import (
    OKResponse,
    PaginatedResponse,
    PatientProfileCreate,
    PatientProfileResponse,
    PatientProfileUpdate,
)
from app.utils.audit import log_action
from app.utils.sync import record_change

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("", response_model=PatientProfileResponse, status_code=status.HTTP_201_CREATED)
async def register_patient(
    body: PatientProfileCreate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new patient (CHW or admin). Idempotent: a user has at most one
    patient profile, so re-registering returns the existing one. A CHW's
    patients default to (and are restricted to) the CHW's facility.
    """
    result = await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == body.user_id)
    )
    if (existing := result.scalar_one_or_none()):
        return existing

    user = await db.get(User, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role != UserRole.patient:
        raise HTTPException(status_code=400, detail="Only patient accounts can have a patient profile.")

    data = body.model_dump(exclude={"idempotency_key"})
    if current_user.role == UserRole.chw:
        data["facility_id"] = current_user.facility_id
    profile = PatientProfile(id=uuid.uuid4(), **data)
    if profile.consent_recorded:
        profile.consent_timestamp = datetime.now(timezone.utc)
    if user.facility_id is None:
        user.facility_id = profile.facility_id
    db.add(profile)
    await record_change(db, "patient_profiles", profile, "insert", current_user.id, body.idempotency_key)
    await log_action(db, current_user.id, "create", "patient_profile", str(profile.id))
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("", response_model=PaginatedResponse)
async def list_patients(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    search: str = Query(None),
    current_user: CHWOrAbove = None,
    db: AsyncSession = Depends(get_db),
):
    """List patients. CHWs see only their facility's patients."""
    query = select(PatientProfile).join(User, PatientProfile.user_id == User.id)

    if current_user.role == UserRole.chw:
        query = query.where(PatientProfile.facility_id == current_user.facility_id)

    if search:
        query = query.where(User.name.ilike(f"%{search}%"))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=page,
        per_page=per_page,
        items=[PatientProfileResponse.model_validate(p) for p in items],
    )


@router.get("/me", response_model=PatientProfileResponse)
async def get_my_patient_profile(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """A patient's own profile (the id their records/appointments use)."""
    profile = await get_own_patient_profile(db, current_user)
    if not profile:
        raise HTTPException(status_code=404, detail="No patient profile for this account.")
    return profile


@router.get("/{patient_id}", response_model=PatientProfileResponse)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    profile = await load_patient_or_404(db, current_user, patient_id)
    await log_action(db, current_user.id, "read", "patient_profile", str(patient_id))
    return profile


@router.patch("/{patient_id}", response_model=PatientProfileResponse)
async def update_patient(
    patient_id: uuid.UUID,
    body: PatientProfileUpdate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    profile = await load_patient_or_404(db, current_user, patient_id)

    for field, value in body.model_dump(exclude_none=True, exclude={"idempotency_key"}).items():
        setattr(profile, field, value)

    await record_change(db, "patient_profiles", profile, "update", current_user.id, body.idempotency_key)
    await log_action(db, current_user.id, "update", "patient_profile", str(patient_id))
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{patient_id}/records")
async def get_patient_records(
    patient_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return full health timeline: encounters + prescriptions."""
    await load_patient_or_404(db, current_user, patient_id)
    result = await db.execute(
        select(Encounter)
        .where(Encounter.patient_id == patient_id)
        .options(selectinload(Encounter.prescriptions))
        .order_by(Encounter.encounter_date.desc())
    )
    encounters = result.scalars().all()
    await log_action(db, current_user.id, "read", "patient_records", str(patient_id))
    return {"encounters": encounters}


@router.post("/{patient_id}/consent", response_model=OKResponse)
async def record_consent(
    patient_id: uuid.UUID,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """Record patient consent at registration."""
    profile = await load_patient_or_404(db, current_user, patient_id)
    profile.consent_recorded = True
    profile.consent_timestamp = datetime.now(timezone.utc)
    await record_change(db, "patient_profiles", profile, "update", current_user.id)
    await log_action(db, current_user.id, "update", "patient_consent", str(patient_id))
    await db.commit()
    return OKResponse(message="Consent recorded.")
