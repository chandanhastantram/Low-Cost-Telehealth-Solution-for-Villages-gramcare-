"""
GramCare – FastAPI dependency injection helpers

• get_current_user   – validates Bearer JWT, returns User ORM object
• require_roles      – role-based access control decorator factory
• get_redis          – yields Redis client
"""

import uuid
from typing import Annotated, List

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


# ── Redis ─────────────────────────────────────────────────────────────────────

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


# ── Current user ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


# ── Role-based access control ─────────────────────────────────────────────────

def require_roles(*roles: UserRole):
    """Factory returning a dependency that raises 403 if role not allowed."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action.",
            )
        return current_user
    return _check


# ── Shorthands ────────────────────────────────────────────────────────────────

CurrentUser = Annotated[User, Depends(get_current_user)]
AdminOrDoctor = Annotated[User, Depends(require_roles(UserRole.admin, UserRole.doctor))]
CHWOrAbove = Annotated[User, Depends(require_roles(UserRole.chw, UserRole.doctor, UserRole.admin))]
AdminOnly = Annotated[User, Depends(require_roles(UserRole.admin))]
