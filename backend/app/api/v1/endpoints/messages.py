"""
GramCare – Chat history endpoint

Live messages are delivered over Socket.IO ("chat:message", see
app/realtime/socketio_app.py); this REST endpoint lets a participant who
reconnects, or was offline when messages were sent, fetch the backlog.

GET /api/v1/messages/{appointment_id} – list chat history for an appointment
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import load_appointment_or_404
from app.core.deps import CurrentUser, get_db
from app.models.models import ChatMessage
from app.schemas.schemas import ChatMessageResponse

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get("/{appointment_id}", response_model=List[ChatMessageResponse])
async def get_message_history(
    appointment_id: uuid.UUID,
    current_user: CurrentUser,
    since: str = Query(None, description="ISO timestamp; only messages after this"),
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
):
    await load_appointment_or_404(db, current_user, appointment_id)

    query = select(ChatMessage).where(ChatMessage.appointment_id == appointment_id)
    if since:
        from datetime import datetime
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail="`since` must be an ISO timestamp.")
        query = query.where(ChatMessage.created_at > since_dt)

    result = await db.execute(query.order_by(ChatMessage.created_at.asc()).limit(limit))
    return result.scalars().all()
