"""
GramCare – Auth endpoints
POST /api/v1/auth/otp/request   – send OTP
POST /api/v1/auth/otp/verify    – verify OTP → issue tokens
POST /api/v1/auth/refresh        – rotate refresh token
POST /api/v1/auth/logout         – revoke refresh token
"""

import logging
import random
import string
from datetime import datetime, timedelta, timezone

import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.deps import CurrentUser, get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_secret,
    hash_token,
    verify_secret,
)
from app.db.session import get_db
from app.models.models import (
    DoctorProfile,
    OTPRecord,
    PatientProfile,
    RefreshToken,
    User,
    UserRole,
)
from app.schemas.schemas import (
    OKResponse,
    OTPRequestSchema,
    OTPVerifySchema,
    RefreshTokenSchema,
    TokenResponse,
)
from app.services.otp_service import send_otp_sms
from app.utils.audit import log_action

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _rate_limit_otp(phone: str, redis) -> None:
    """Best-effort rate limiting. Redis is a non-essential service on a
    single-VM low-cost deployment — if it's unreachable, log it and let the
    OTP request through rather than taking down the entire login flow."""
    key = f"otp_rate:{phone}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 3600)
    except redis_exceptions.RedisError as e:
        logger.warning(f"OTP rate limiting skipped (Redis unavailable): {e}")
        return
    if count > settings.RATE_LIMIT_OTP_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Try again in an hour.",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/otp/request", response_model=OKResponse)
async def request_otp(
    body: OTPRequestSchema,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Request an OTP to the given phone number.
    If the user doesn't exist and a name is provided, a new user record is created.
    """
    await _rate_limit_otp(body.phone, redis)

    # Ensure user record exists
    result = await db.execute(select(User).where(User.phone == body.phone))
    user = result.scalar_one_or_none()
    if not user:
        if not body.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name is required for new users.",
            )
        user = User(phone=body.phone, name=body.name)
        db.add(user)
        await db.flush()

    # Generate & store OTP
    otp_code = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    otp_record = OTPRecord(
        phone=body.phone,
        otp_hash=hash_secret(otp_code),
        expires_at=expires_at,
    )
    db.add(otp_record)
    await db.commit()

    # Send / log OTP
    await send_otp_sms(body.phone, otp_code)

    return OKResponse(message="OTP sent successfully.")


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(
    body: OTPVerifySchema,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Verify OTP and issue access + refresh tokens."""
    now = datetime.now(timezone.utc)

    # Find latest non-expired, unverified OTP for this phone
    result = await db.execute(
        select(OTPRecord)
        .where(
            OTPRecord.phone == body.phone,
            OTPRecord.verified.is_(False),
            OTPRecord.expires_at > now,
        )
        .order_by(OTPRecord.created_at.desc())
        .limit(1)
    )
    otp_record = result.scalar_one_or_none()
    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired or not found.")

    # Brute-force protection
    otp_record.attempt_count = (otp_record.attempt_count or 0) + 1
    if otp_record.attempt_count > 5:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed attempts.")

    if not verify_secret(body.otp, otp_record.otp_hash):
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

    otp_record.verified = True

    # Fetch user
    result = await db.execute(select(User).where(User.phone == body.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Issue tokens
    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    raw_refresh = create_refresh_token()

    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
    await db.commit()

    await log_action(db, user.id, "login", "user", str(user.id), {"phone": body.phone})

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user.id),
        role=user.role.value,
        name=user.name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    body: RefreshTokenSchema,
    db: AsyncSession = Depends(get_db),
):
    """Rotate refresh token."""
    token_hash = hash_token(body.refresh_token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > now,
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")

    # Revoke old token
    rt.revoked = True

    result = await db.execute(select(User).where(User.id == rt.user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    raw_refresh = create_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_rt)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user.id),
        role=user.role.value,
        name=user.name,
    )


@router.post("/logout", response_model=OKResponse)
async def logout(
    body: RefreshTokenSchema,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """Revoke refresh token."""
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
        await db.commit()
    return OKResponse(message="Logged out.")


# ── Dev-only instant login (OTP bypass) ────────────────────────────────────
# Skips OTP entirely and logs straight into one of three canned demo
# accounts. Only enabled while settings.DEBUG is true (never in prod — see
# the 404 guard below) so this can't become an auth bypass in a real
# deployment. Each role gets a fixed demo phone number; the account and its
# role-specific profile (patient/doctor) are created on first use.
_DEV_DEMO_ACCOUNTS = {
    UserRole.admin: {"phone": "+910000000001", "name": "Admin Demo"},
    UserRole.doctor: {"phone": "+910000000002", "name": "Dr Demo"},
    UserRole.patient: {"phone": "+910000000003", "name": "Patient Demo"},
    UserRole.chw: {"phone": "+910000000004", "name": "CHW Demo"},
}


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(role: UserRole, db: AsyncSession = Depends(get_db)):
    if not settings.DEBUG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if role not in _DEV_DEMO_ACCOUNTS:
        raise HTTPException(status_code=400, detail="No demo account for this role.")

    demo = _DEV_DEMO_ACCOUNTS[role]
    result = await db.execute(select(User).where(User.phone == demo["phone"]))
    user = result.scalar_one_or_none()
    if not user:
        user = User(phone=demo["phone"], name=demo["name"], role=role)
        db.add(user)
        await db.flush()
    elif user.role != role:
        user.role = role

    if role == UserRole.patient:
        existing = await db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
        if not existing.scalar_one_or_none():
            db.add(PatientProfile(user_id=user.id, consent_recorded=True))
    elif role == UserRole.doctor:
        existing = await db.execute(select(DoctorProfile).where(DoctorProfile.user_id == user.id))
        if not existing.scalar_one_or_none():
            db.add(DoctorProfile(user_id=user.id, specialization="General Medicine"))

    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    raw_refresh = create_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()

    await log_action(db, user.id, "login", "user", str(user.id), {"dev_login": True})

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user.id),
        role=user.role.value,
        name=user.name,
    )
