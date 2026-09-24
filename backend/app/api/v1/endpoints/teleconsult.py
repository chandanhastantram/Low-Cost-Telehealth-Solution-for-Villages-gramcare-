"""
GramCare – Teleconsultation endpoints (peer-to-peer WebRTC)

POST /api/v1/teleconsult/room          – get/create the call room + ICE config
                                          (actual offer/answer/ICE signaling
                                          happens over Socket.IO, see
                                          app/realtime/socketio_app.py)
GET  /api/v1/teleconsult/ice-servers   – TURN/STUN ICE server config
POST /api/v1/teleconsult/store-forward – submit a store-and-forward bundle
GET  /api/v1/teleconsult/store-forward – list pending S&F cases (doctor)
POST /api/v1/teleconsult/store-forward/{id}/respond – doctor responds

No SFU/media server is used: doctor and patient/CHW connect directly
(audio-first, video optional) once Socket.IO has relayed their SDP offer/
answer and ICE candidates. This keeps the whole call path free — only a
self-hosted, open-source coturn TURN server is needed as a fallback for
strict NATs.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser, get_db, require_roles
from app.models.models import (
    Appointment,
    AppointmentStatus,
    StoreForwardBundle,
    UserRole,
)
from app.schemas.schemas import (
    CallRoomRequest,
    CallRoomResponse,
    StoreForwardCreate,
    StoreForwardResponse,
)
from app.utils.audit import log_action

router = APIRouter(prefix="/teleconsult", tags=["Teleconsultation"])


def _ice_servers() -> list[dict]:
    servers = [{"urls": settings.stun_urls}]
    if settings.TURN_ENABLED:
        servers.append(
            {
                "urls": [settings.TURN_URL],
                "username": settings.TURN_USERNAME,
                "credential": settings.TURN_CREDENTIAL,
            }
        )
    return servers


@router.post("/room", response_model=CallRoomResponse)
async def get_call_room(
    body: CallRoomRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the Socket.IO room name + ICE server config for an appointment.
    Both sides join this room over Socket.IO ("call:join") and exchange
    SDP/ICE via "call:signal"; the browser/app then opens a direct P2P
    WebRTC connection — no token or media server involved.
    """
    result = await db.execute(
        select(Appointment).where(Appointment.id == body.appointment_id)
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if appt.status not in [AppointmentStatus.confirmed, AppointmentStatus.pending]:
        raise HTTPException(status_code=400, detail="Appointment is not active.")

    if not appt.call_room_name:
        appt.call_room_name = f"gramcare-{appt.id}"
        await db.commit()

    await log_action(db, current_user.id, "read", "teleconsult_room", str(body.appointment_id))

    return CallRoomResponse(room_name=appt.call_room_name, ice_servers=_ice_servers())


@router.get("/ice-servers")
async def get_ice_servers(current_user: CurrentUser):
    """Return TURN/STUN ICE server configuration."""
    return {"ice_servers": _ice_servers()}


# ── Store-and-Forward ─────────────────────────────────────────────────────────

@router.post(
    "/store-forward",
    response_model=StoreForwardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_store_forward(
    body: StoreForwardCreate,
    current_user=Depends(require_roles(UserRole.chw, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    CHW submits a store-and-forward case bundle when live call is not possible.
    The bundle contains structured complaint data, vitals, photo/voice note URLs.
    """
    # Idempotency check
    if body.idempotency_key:
        result = await db.execute(
            select(StoreForwardBundle).where(
                StoreForwardBundle.idempotency_key == body.idempotency_key
            )
        )
        if (existing := result.scalar_one_or_none()):
            return existing

    bundle = StoreForwardBundle(
        encounter_id=body.encounter_id,
        patient_id=body.patient_id,
        chw_id=current_user.id,
        payload_json=body.payload_json,
        idempotency_key=body.idempotency_key,
        status="queued",
    )
    db.add(bundle)
    await db.commit()
    await db.refresh(bundle)
    await log_action(db, current_user.id, "create", "store_forward", str(bundle.id))
    return bundle


@router.get("/store-forward", response_model=List[StoreForwardResponse])
async def list_store_forward(
    status_filter: str = Query("queued"),
    current_user=Depends(require_roles(UserRole.doctor, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    Doctor lists store-and-forward cases. Queued cases have no doctor_id yet
    (any doctor can pick one up), so only filter by doctor_id for cases
    already claimed/replied — otherwise a freshly submitted case would be
    invisible to every doctor forever.
    """
    query = select(StoreForwardBundle).where(StoreForwardBundle.status == status_filter)
    if current_user.role == UserRole.doctor and status_filter != "queued":
        query = query.where(StoreForwardBundle.doctor_id == current_user.id)
    result = await db.execute(query.order_by(StoreForwardBundle.created_at.asc()))
    return result.scalars().all()


@router.post("/store-forward/{bundle_id}/respond", response_model=StoreForwardResponse)
async def respond_to_store_forward(
    bundle_id: uuid.UUID,
    response_text: str,
    current_user=Depends(require_roles(UserRole.doctor, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Doctor responds to a store-and-forward case."""
    result = await db.execute(
        select(StoreForwardBundle).where(StoreForwardBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found.")

    bundle.doctor_id = current_user.id
    bundle.doctor_response = response_text
    bundle.status = "replied"
    bundle.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(bundle)
    await log_action(db, current_user.id, "update", "store_forward", str(bundle_id))
    return bundle
