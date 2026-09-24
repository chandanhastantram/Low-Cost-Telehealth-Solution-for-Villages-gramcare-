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

from app.core.deps import CurrentUser, get_db
from app.models.models import (
    Appointment,
    ChatMessage,
    DoctorProfile,
    PatientProfile,
    UserRole,
)
from app.schemas.schemas import ChatMessageResponse

router = APIRouter(prefix="/messages", tags=["Messages"])


async def _assert_can_access(current_user, appointment: Appointment, db: AsyncSession) -> None:
    if current_user.role == UserRole.admin:
        return
    if current_user.role == UserRole.chw and appointment.chw_id == current_user.id:
        return
    if current_user.role == UserRole.doctor:
        doc = (
            await db.execute(select(DoctorProfile).where(DoctorProfile.user_id == current_user.id))
        ).scalar_one_or_none()
        if doc and appointment.doctor_id == doc.id:
            return
    if current_user.role == UserRole.patient:
        pat = (
            await db.execute(select(PatientProfile).where(PatientProfile.user_id == current_user.id))
        ).scalar_one_or_none()
        if pat and appointment.patient_id == pat.id:
            return
    raise HTTPException(status_code=403, detail="Not authorized for this appointment's messages.")


@router.get("/{appointment_id}", response_model=List[ChatMessageResponse])
async def get_message_history(
    appointment_id: uuid.UUID,
    current_user: CurrentUser,
    since: str = Query(None, description="ISO timestamp; only messages after this"),
    limit: int = Query(200, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    await _assert_can_access(current_user, appointment, db)

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
