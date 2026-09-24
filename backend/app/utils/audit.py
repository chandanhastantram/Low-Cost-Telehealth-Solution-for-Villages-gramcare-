"""
GramCare – Audit logging utility
"""

import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, AuditAction


async def log_action(
    db: AsyncSession,
    actor_id: Optional[uuid.UUID],
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Append an audit log entry. Never raises — audit failures are logged only."""
    try:
        log = AuditLog(
            actor_id=actor_id,
            action=AuditAction(action),
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log)
        # Don't commit here — caller handles the commit
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Audit log failed: {e}")
