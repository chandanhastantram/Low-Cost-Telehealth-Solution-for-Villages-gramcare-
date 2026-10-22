"""
GramCare – Real-time layer: WebRTC call signaling + in-consultation chat.

Cost-cutting design: this single Socket.IO server does both jobs so no
separate signaling service or SFU is needed —

  • Call signaling (peer-to-peer WebRTC, audio-first):
      client -> "call:join"   {appointment_id}
      client -> "call:signal" {appointment_id, data}   # relayed verbatim
      client -> "call:leave"  {appointment_id}
    The server never inspects the SDP/ICE payload; it just relays it to the
    other participant in the same appointment room. Media then flows
    directly between the two devices (through TURN only if a direct path
    fails), so no per-minute media-server cost is incurred.

  • Chat ("message socket.io"):
      client -> "chat:join"    {appointment_id}
      client -> "chat:message" {appointment_id, body, idempotency_key?}
    Messages are persisted (ChatMessage) so a participant who reconnects –
    or was offline, per the paper's offline-first design – can fetch
    history via GET /api/v1/messages/{appointment_id}.

A single in-memory AsyncServer is enough for a single-VM pilot deployment
(per the paper's low-cost deployment target); swap in the Redis manager
(`socketio.AsyncRedisManager`) only if the app ever needs to scale beyond
one process.
"""

import uuid
from typing import Any, Optional

import socketio
from jose import JWTError
from sqlalchemy import select

from app.core.access import can_access_appointment
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.models import Appointment, ChatMessage, User

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


def _call_room(appointment_id: str) -> str:
    return f"call:{appointment_id}"


def _chat_room(appointment_id: str) -> str:
    return f"chat:{appointment_id}"


async def _authenticate(auth: Optional[dict]) -> Optional[User]:
    token = (auth or {}).get("token") if auth else None
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()


async def _can_access_appointment(user: User, appointment_id: str) -> bool:
    """Same rules as the REST API (app/core/access.py)."""
    try:
        appt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        return False
    async with AsyncSessionLocal() as db:
        appt = await db.get(Appointment, appt_uuid)
        return bool(appt and await can_access_appointment(db, user, appt))


# ── Connection lifecycle ───────────────────────────────────────────────────

@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict] = None):
    user = await _authenticate(auth)
    if not user:
        raise ConnectionRefusedError("Authentication failed: missing/invalid JWT.")
    await sio.save_session(sid, {"user_id": str(user.id), "role": user.role.value})


@sio.event
async def disconnect(sid: str):
    # socket.io removes the sid from all rooms automatically; nothing to persist.
    pass


# ── Call signaling ─────────────────────────────────────────────────────────

@sio.on("call:join")
async def call_join(sid: str, data: dict):
    session = await sio.get_session(sid)
    appointment_id = str(data.get("appointment_id", ""))
    user = await _load_user(session)
    if not user or not await _can_access_appointment(user, appointment_id):
        await sio.emit("call:error", {"message": "Not authorized for this appointment."}, to=sid)
        return
    room = _call_room(appointment_id)
    await sio.enter_room(sid, room)
    await sio.emit("call:peer-joined", {"appointment_id": appointment_id}, room=room, skip_sid=sid)


@sio.on("call:signal")
async def call_signal(sid: str, data: dict):
    """Relay an SDP offer/answer or ICE candidate to the other peer verbatim."""
    appointment_id = str(data.get("appointment_id", ""))
    payload: Any = data.get("data")
    room = _call_room(appointment_id)
    # Only a socket that passed the call:join authorization may signal into
    # the room — otherwise anyone could inject SDP into someone else's call.
    if room not in sio.rooms(sid):
        await sio.emit("call:error", {"message": "Join the call before signaling."}, to=sid)
        return
    await sio.emit(
        "call:signal",
        {"appointment_id": appointment_id, "data": payload},
        room=room,
        skip_sid=sid,
    )


@sio.on("call:leave")
async def call_leave(sid: str, data: dict):
    appointment_id = str(data.get("appointment_id", ""))
    room = _call_room(appointment_id)
    if room not in sio.rooms(sid):
        return
    await sio.emit("call:peer-left", {"appointment_id": appointment_id}, room=room, skip_sid=sid)
    await sio.leave_room(sid, room)


# ── Chat ──────────────────────────────────────────────────────────────────

@sio.on("chat:join")
async def chat_join(sid: str, data: dict):
    session = await sio.get_session(sid)
    appointment_id = str(data.get("appointment_id", ""))
    user = await _load_user(session)
    if not user or not await _can_access_appointment(user, appointment_id):
        await sio.emit("chat:error", {"message": "Not authorized for this appointment."}, to=sid)
        return
    await sio.enter_room(sid, _chat_room(appointment_id))


@sio.on("chat:message")
async def chat_message(sid: str, data: dict):
    session = await sio.get_session(sid)
    user = await _load_user(session)
    if not user:
        await sio.emit("chat:error", {"message": "Not authenticated."}, to=sid)
        return

    appointment_id = str(data.get("appointment_id", ""))
    body = (data.get("body") or "").strip()
    idempotency_key = data.get("idempotency_key")
    if not body or not await _can_access_appointment(user, appointment_id):
        await sio.emit("chat:error", {"message": "Invalid message or not authorized."}, to=sid)
        return

    async with AsyncSessionLocal() as db:
        if idempotency_key:
            existing = (
                await db.execute(
                    select(ChatMessage).where(ChatMessage.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
            if existing:
                message = existing
            else:
                message = ChatMessage(
                    appointment_id=uuid.UUID(appointment_id),
                    sender_id=user.id,
                    body=body[:4000],
                    idempotency_key=idempotency_key,
                )
                db.add(message)
                await db.commit()
                await db.refresh(message)
        else:
            message = ChatMessage(
                appointment_id=uuid.UUID(appointment_id),
                sender_id=user.id,
                body=body[:4000],
            )
            db.add(message)
            await db.commit()
            await db.refresh(message)

    payload = {
        "id": str(message.id),
        "appointment_id": appointment_id,
        "sender_id": str(message.sender_id),
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }
    await sio.emit("chat:message", payload, room=_chat_room(appointment_id))


async def _load_user(session: Optional[dict]) -> Optional[User]:
    if not session or "user_id" not in session:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == uuid.UUID(session["user_id"]), User.is_active.is_(True))
        )
        return result.scalar_one_or_none()
