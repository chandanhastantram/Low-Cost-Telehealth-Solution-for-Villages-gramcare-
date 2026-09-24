"""
GramCare – JWT + OTP authentication core
"""

import hashlib
import random
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password / PIN hashing ─────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def verify_secret(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_token(token: str) -> str:
    """SHA-256 of a refresh token for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── OTP ───────────────────────────────────────────────────────────────────────

def generate_otp(length: int = settings.OTP_LENGTH) -> str:
    return "".join(random.choices(string.digits, k=length))


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    payload = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> str:
    """Opaque random token stored hashed in DB."""
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict:
    """Raises JWTError on invalid / expired tokens."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
