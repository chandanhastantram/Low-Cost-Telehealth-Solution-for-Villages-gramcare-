"""
GramCare – Patient endpoints
GET    /api/v1/patients              – list (CHW sees own facility)
POST   /api/v1/patients              – register patient
GET    /api/v1/patients/{id}         – get patient
PATCH  /api/v1/patients/{id}         – update patient
GET    /api/v1/patients/{id}/records – full health timeline
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CHWOrAbove, CurrentUser, get_db, require_roles
from app.models.models import (
    Encounter,
    PatientProfile,
    Prescription,
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
from app.utils.sync import bump_version

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("", response_model=PatientProfileResponse, status_code=status.HTTP_201_CREATED)
async def register_patient(
    body: PatientProfileCreate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """Register a new patient (CHW or admin). Idempotent via idempotency_key."""
    # Idempotency check
    if body.idempotency_key:
        result = await db.execute(
            select(PatientProfile).where(PatientProfile.user_id == body.user_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    profile = PatientProfile(**body.model_dump(exclude={"idempotency_key"}))
    profile.server_version = await bump_version(db, "patient_profiles")
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    await log_action(db, current_user.id, "create", "patient_profile", str(profile.id))
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

    # CHW sees only own facility
    if current_user.role == UserRole.chw and current_user.facility_id:
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


@router.get("/{patient_id}", response_model=PatientProfileResponse)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PatientProfile).where(PatientProfile.id == patient_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Patient not found.")

    # CHW: ensure same facility
    if current_user.role == UserRole.chw:
        if profile.facility_id != current_user.facility_id:
            raise HTTPException(status_code=403, detail="Access denied.")

    await log_action(db, current_user.id, "read", "patient_profile", str(patient_id))
    return profile


@router.patch("/{patient_id}", response_model=PatientProfileResponse)
async def update_patient(
    patient_id: uuid.UUID,
    body: PatientProfileUpdate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PatientProfile).where(PatientProfile.id == patient_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Patient not found.")

    for field, value in body.model_dump(exclude_none=True, exclude={"idempotency_key"}).items():
        setattr(profile, field, value)

    profile.server_version = await bump_version(db, "patient_profiles")
    await db.commit()
    await db.refresh(profile)
    await log_action(db, current_user.id, "update", "patient_profile", str(patient_id))
    return profile


@router.get("/{patient_id}/records")
async def get_patient_records(
    patient_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Return full health timeline: encounters + prescriptions."""
    result = await db.execute(
        select(Encounter)
        .where(Encounter.patient_id == patient_id)
        .options(selectinload(Encounter.prescriptions))
        .order_by(Encounter.encounter_date.desc())
    )
    encounters = result.scalars().all()
    return {"encounters": encounters}


@router.post("/{patient_id}/consent", response_model=OKResponse)
async def record_consent(
    patient_id: uuid.UUID,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """Record patient consent at registration."""
    from datetime import datetime, timezone
    result = await db.execute(select(PatientProfile).where(PatientProfile.id == patient_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Patient not found.")
    profile.consent_recorded = True
    profile.consent_timestamp = datetime.now(timezone.utc)
    await db.commit()
    await log_action(db, current_user.id, "update", "patient_consent", str(patient_id))
    return OKResponse(message="Consent recorded.")
