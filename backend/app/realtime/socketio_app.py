"""
GramCare – Real-time layer: WebRTC call signaling + in-consultation chat.

Cost-cutting design: this single Socket.IO server does both jobs so no
separate signaling service or SFU is needed —

  • Call signaling (peer-to-peer WebRTC, audio-first):
      client -> "call:join"   {appointment_id}
      client -> "call:signal" {appointment_id, data}   # relayed verbatim (+ "from")
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
#
# Rural links drop constantly, so clients reconnect and simply re-send
# call:join / chat:join; every handler here is safe to repeat.

@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict] = None):
    user = await _authenticate(auth)
    if not user:
        raise ConnectionRefusedError("Authentication failed: missing/invalid JWT.")
    await sio.save_session(sid, {"user_id": str(user.id), "role": user.role.value})


@sio.event
async def disconnect(sid: str, *args):
    # Tell call peers this side dropped (it may come back) rather than left.
    session = await sio.get_session(sid)
    for room in sio.rooms(sid):
        if room.startswith("call:"):
            await sio.emit(
                "call:peer-offline",
                {"appointment_id": room.split(":", 1)[1], "from": session.get("user_id")},
                room=room,
                skip_sid=sid,
            )


def _peers_in(room: str, sid: str) -> int:
    return sum(1 for other, _ in sio.manager.get_participants("/", room) if other != sid)


# ── Call signaling ─────────────────────────────────────────────────────────

@sio.on("call:join")
async def call_join(sid: str, data: dict):
    """Ack: {"ok": bool, "peers": int} — peers already waiting in the call."""
    session = await sio.get_session(sid)
    appointment_id = str(data.get("appointment_id", ""))
    user = await _load_user(session)
    if not user or not await _can_access_appointment(user, appointment_id):
        await sio.emit("call:error", {"message": "Not authorized for this appointment."}, to=sid)
        return {"ok": False, "peers": 0}
    room = _call_room(appointment_id)
    await sio.enter_room(sid, room)
    await sio.emit(
        "call:peer-joined",
        {"appointment_id": appointment_id, "from": session["user_id"]},
        room=room,
        skip_sid=sid,
    )
    return {"ok": True, "peers": _peers_in(room, sid)}


@sio.on("call:signal")
async def call_signal(sid: str, data: dict):
    """Relay an SDP description or ICE candidate to the other peer verbatim."""
    appointment_id = str(data.get("appointment_id", ""))
    payload: Any = data.get("data")
    room = _call_room(appointment_id)
    # Only a socket that passed the call:join authorization may signal into
    # the room — otherwise anyone could inject SDP into someone else's call.
    if room not in sio.rooms(sid):
        await sio.emit("call:error", {"message": "Join the call before signaling."}, to=sid)
        return
    session = await sio.get_session(sid)
    await sio.emit(
        "call:signal",
        {"appointment_id": appointment_id, "data": payload, "from": session["user_id"]},
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
        return {"ok": False}
    await sio.enter_room(sid, _chat_room(appointment_id))
    return {"ok": True}


@sio.on("chat:typing")
async def chat_typing(sid: str, data: dict):
    appointment_id = str(data.get("appointment_id", ""))
    room = _chat_room(appointment_id)
    if room not in sio.rooms(sid):
        return
    session = await sio.get_session(sid)
    await sio.emit(
        "chat:typing",
        {"appointment_id": appointment_id, "from": session["user_id"], "typing": bool(data.get("typing"))},
        room=room,
        skip_sid=sid,
    )


@sio.on("chat:message")
async def chat_message(sid: str, data: dict):
    """
    Persist and broadcast. Ack: {"ok": True, "message": {...}} so the sender
    can mark it delivered; re-sending the same idempotency_key after a
    reconnect returns the stored message instead of a duplicate.
    """
    session = await sio.get_session(sid)
    user = await _load_user(session)
    if not user:
        return {"ok": False, "error": "Not authenticated."}

    appointment_id = str(data.get("appointment_id", ""))
    body = (data.get("body") or "").strip()
    idempotency_key = data.get("idempotency_key") or None
    if not body or not await _can_access_appointment(user, appointment_id):
        return {"ok": False, "error": "Invalid message or not authorized."}

    async with AsyncSessionLocal() as db:
        message = None
        if idempotency_key:
            message = (
                await db.execute(
                    select(ChatMessage).where(ChatMessage.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
        if message is None:
            message = ChatMessage(
                appointment_id=uuid.UUID(appointment_id),
                sender_id=user.id,
                body=body[:4000],
                idempotency_key=idempotency_key,
            )
            db.add(message)
            await db.commit()
            await db.refresh(message)

    payload = {
        "id": str(message.id),
        "appointment_id": appointment_id,
        "sender_id": str(message.sender_id),
        "body": message.body,
        "idempotency_key": message.idempotency_key,
        "created_at": message.created_at.isoformat(),
    }
    await sio.emit("chat:message", payload, room=_chat_room(appointment_id), skip_sid=sid)
    return {"ok": True, "message": payload}


async def _load_user(session: Optional[dict]) -> Optional[User]:
    if not session or "user_id" not in session:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == uuid.UUID(session["user_id"]), User.is_active.is_(True))
        )
        return result.scalar_one_or_none()
