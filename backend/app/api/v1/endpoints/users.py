"""
GramCare – Admin & User management endpoints

GET    /api/v1/users/me           – get current user profile
PATCH  /api/v1/users/me           – update name / language
PUT    /api/v1/users/me/pin       – set offline unlock PIN
POST   /api/v1/users/me/pin/verify – check offline PIN (rate limited)
DELETE /api/v1/users/me/pin       – remove offline PIN
GET    /api/v1/users              – list users (staff)
PATCH  /api/v1/users/{id}         – change role / facility / status (admin)
POST   /api/v1/facilities         – create facility (admin)
GET    /api/v1/facilities         – list facilities
GET    /api/v1/audit-logs         – view audit logs (admin)
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.exceptions as redis_exceptions

from app.core.deps import AdminOnly, CHWOrAbove, CurrentUser, get_db, get_redis
from app.core.security import hash_secret, verify_secret
from app.models.models import AuditLog, CHWProfile, DoctorProfile, Facility, User, UserRole
from app.schemas.schemas import (
    AdminUserUpdate,
    OKResponse,
    PinSetRequest,
    PinVerifyRequest,
    PinVerifyResponse,
    CHWProfileCreate,
    CHWProfileResponse,
    DoctorProfileCreate,
    DoctorProfileResponse,
    FacilityCreate,
    FacilityResponse,
    PaginatedResponse,
    UserResponse,
    UserUpdate,
)
from app.utils.audit import log_action

router = APIRouter(tags=["Users & Admin"])


# ── Current User ──────────────────────────────────────────────────────────────

@router.get("/users/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user


@router.patch("/users/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ── Offline PIN ───────────────────────────────────────────────────────────────
# The device keeps its own salted hash of the PIN so the app can be unlocked
# with no network (paper §9, lost/stolen device). The server copy lets a
# replacement device re-verify the PIN and caps guessing to PIN_MAX_ATTEMPTS
# per window; after that the user must log in again with an OTP.

PIN_MAX_ATTEMPTS = 5
PIN_LOCK_SECONDS = 15 * 60


@router.put("/users/me/pin", response_model=OKResponse)
async def set_offline_pin(
    body: PinSetRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    current_user.device_pin_hash = hash_secret(body.pin)
    await log_action(db, current_user.id, "update", "user_pin", str(current_user.id))
    await db.commit()
    return OKResponse(message="Offline PIN set.")


@router.delete("/users/me/pin", response_model=OKResponse)
async def clear_offline_pin(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    current_user.device_pin_hash = None
    await log_action(db, current_user.id, "delete", "user_pin", str(current_user.id))
    await db.commit()
    return OKResponse(message="Offline PIN removed.")


@router.post("/users/me/pin/verify", response_model=PinVerifyResponse)
async def verify_offline_pin(
    body: PinVerifyRequest,
    current_user: CurrentUser,
    redis=Depends(get_redis),
):
    if not current_user.device_pin_hash:
        raise HTTPException(status_code=404, detail="No offline PIN set.")

    key = f"pin_fail:{current_user.id}"
    try:
        failures = int(await redis.get(key) or 0)
    except redis_exceptions.RedisError:
        failures = 0  # Redis is best-effort on a single-VM deployment
    if failures >= PIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many wrong PINs. Log in again with OTP.")

    if verify_secret(body.pin, current_user.device_pin_hash):
        try:
            await redis.delete(key)
        except redis_exceptions.RedisError:
            pass
        return PinVerifyResponse(valid=True, attempts_remaining=PIN_MAX_ATTEMPTS)

    try:
        failures = await redis.incr(key)
        if failures == 1:
            await redis.expire(key, PIN_LOCK_SECONDS)
    except redis_exceptions.RedisError:
        failures += 1
    return PinVerifyResponse(valid=False, attempts_remaining=max(PIN_MAX_ATTEMPTS - failures, 0))


# ── Staff directory ────────────────────────────────────────────────────────
# CHW/doctor/admin (not patients) can look users up by phone — this is how a
# CHW finds the user record for a patient they just onboarded via OTP
# request, before calling POST /patients with that user_id.

@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    role: Optional[UserRole] = None,
    facility_id: Optional[uuid.UUID] = None,
    phone: Optional[str] = None,
    current_user: CHWOrAbove = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if facility_id:
        query = query.where(User.facility_id == facility_id)
    if phone:
        query = query.where(User.phone.ilike(f"%{phone}%"))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    items = result.scalars().all()

    return PaginatedResponse(
        total=total, page=page, per_page=per_page,
        items=[UserResponse.model_validate(u) for u in items],
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    current_user: AdminOnly,
    db: AsyncSession = Depends(get_db),
):
    """Admin: assign a facility, change role, or (de)activate a user."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if body.facility_id and not await db.get(Facility, body.facility_id):
        raise HTTPException(status_code=404, detail="Facility not found.")
    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(user, field, value)
    await log_action(
        db, current_user.id, "update", "user", str(user_id),
        {k: str(getattr(v, "value", v)) for k, v in changes.items()},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: AdminOnly,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = False
    await db.commit()
    await log_action(db, current_user.id, "update", "user", str(user_id), {"action": "deactivate"})
    return {"ok": True}


# ── Doctor / CHW onboarding ──────────────────────────────────────────────────
# Booking an appointment needs a doctor_profiles row (appointments.doctor_id
# is a foreign key to it, not to users.id) and CHW-scoped patient listing
# uses a users.facility_id — these endpoints are how an admin actually
# onboards staff after they've signed up via OTP, which nothing else in the
# API previously did.

@router.post("/doctors", response_model=DoctorProfileResponse, status_code=status.HTTP_201_CREATED)
async def onboard_doctor(
    body: DoctorProfileCreate,
    current_user: AdminOnly,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    existing = await db.execute(select(DoctorProfile).where(DoctorProfile.user_id == body.user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Doctor profile already exists for this user.")

    user.role = UserRole.doctor
    profile = DoctorProfile(**body.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    await log_action(db, current_user.id, "create", "doctor_profile", str(profile.id))
    return profile


@router.get("/doctors")
async def list_doctors(
    current_user: CHWOrAbove = None,
    db: AsyncSession = Depends(get_db),
):
    """Doctor directory for booking — id here is doctor_profiles.id, the
    value appointments.doctor_id expects (not users.id)."""
    result = await db.execute(select(DoctorProfile, User).join(User, DoctorProfile.user_id == User.id))
    return [
        {
            "id": str(profile.id),
            "user_id": str(profile.user_id),
            "name": user.name,
            "specialization": profile.specialization,
            "available_from": profile.available_from,
            "available_to": profile.available_to,
        }
        for profile, user in result.all()
    ]


@router.post("/chws", response_model=CHWProfileResponse, status_code=status.HTTP_201_CREATED)
async def onboard_chw(
    body: CHWProfileCreate,
    current_user: AdminOnly,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    existing = await db.execute(select(CHWProfile).where(CHWProfile.user_id == body.user_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="CHW profile already exists for this user.")

    if body.facility_id:
        if not await db.get(Facility, body.facility_id):
            raise HTTPException(status_code=404, detail="Facility not found.")
        user.facility_id = body.facility_id
    user.role = UserRole.chw
    profile = CHWProfile(**body.model_dump(exclude={"facility_id"}))
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    await log_action(db, current_user.id, "create", "chw_profile", str(profile.id))
    return profile


# ── Facilities ─────────────────────────────────────────────────────────────────

@router.post("/facilities", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
async def create_facility(
    body: FacilityCreate,
    current_user: AdminOnly,
    db: AsyncSession = Depends(get_db),
):
    facility = Facility(**body.model_dump())
    db.add(facility)
    await db.commit()
    await db.refresh(facility)
    return facility


@router.get("/facilities", response_model=list[FacilityResponse])
async def list_facilities(
    state: Optional[str] = None,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Facility)
    if state:
        query = query.where(Facility.state.ilike(f"%{state}%"))
    result = await db.execute(query)
    return result.scalars().all()


# ── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, le=200),
    resource_type: Optional[str] = None,
    actor_id: Optional[uuid.UUID] = None,
    current_user: AdminOnly = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    logs = result.scalars().all()

    return PaginatedResponse(
        total=total, page=page, per_page=per_page,
        items=[
            {
                "id": log.id,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "action": log.action.value,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    )
