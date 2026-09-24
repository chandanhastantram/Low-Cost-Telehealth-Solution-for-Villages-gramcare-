"""
GramCare – Sync version management utilities
"""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import SyncChangeLog


async def get_current_version(db: AsyncSession) -> int:
    """Return the highest version number in the change log."""
    result = await db.execute(select(func.max(SyncChangeLog.version)))
    val = result.scalar()
    return val or 0


async def bump_version(db: AsyncSession, table_name: str) -> int:
    """
    Get the next version number for a record being written.
    Uses PostgreSQL sequence for monotonically increasing versions.
    """
    result = await db.execute(text("SELECT nextval('sync_version_seq')"))
    return result.scalar()
