"""
GramCare – Doctor slot scheduling

Shared by the REST booking endpoint and /sync/upload so an offline-created
booking gets exactly the same conflict check (and the same alternative-slot
suggestions, per paper §8.2) as an online one.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Appointment, AppointmentStatus, DoctorProfile

SLOT_MINUTES = 15
_INACTIVE = [AppointmentStatus.cancelled, AppointmentStatus.no_show]


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes (SQLite, some clients) as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


async def _hours(db: AsyncSession, doctor_id: uuid.UUID) -> tuple[tuple[int, int], tuple[int, int]]:
    doc = await db.get(DoctorProfile, doctor_id)
    avail_from = (doc and doc.available_from) or "09:00"
    avail_to = (doc and doc.available_to) or "17:00"
    return tuple(map(int, avail_from.split(":"))), tuple(map(int, avail_to.split(":")))


async def _booked_intervals(
    db: AsyncSession, doctor_id: uuid.UUID, start: datetime, end: datetime,
    exclude_id: Optional[uuid.UUID] = None,
) -> list[tuple[datetime, datetime]]:
    # Widen the window by a day so long appointments starting just before it count.
    query = select(Appointment).where(
        and_(
            Appointment.doctor_id == doctor_id,
            Appointment.status.notin_(_INACTIVE),
            Appointment.scheduled_at >= start - timedelta(days=1),
            Appointment.scheduled_at < end,
        )
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    rows = (await db.execute(query)).scalars().all()
    return [
        (as_utc(a.scheduled_at), as_utc(a.scheduled_at) + timedelta(minutes=a.duration_minutes or SLOT_MINUTES))
        for a in rows
    ]


def _overlaps(start: datetime, end: datetime, intervals) -> bool:
    return any(s < end and start < e for s, e in intervals)


async def is_slot_free(
    db: AsyncSession, doctor_id: uuid.UUID, start: datetime, duration_minutes: int = SLOT_MINUTES,
    exclude_id: Optional[uuid.UUID] = None,
) -> bool:
    start = as_utc(start)
    end = start + timedelta(minutes=duration_minutes)
    return not _overlaps(start, end, await _booked_intervals(db, doctor_id, start, end, exclude_id))


def clinic_tz() -> timezone:
    return timezone(timedelta(minutes=settings.CLINIC_UTC_OFFSET_MINUTES))


async def available_slots(db: AsyncSession, doctor_id: uuid.UUID, day: date) -> list[datetime]:
    """Free slots (UTC) on `day`, a clinic-local calendar date."""
    (fh, fm), (th, tm) = await _hours(db, doctor_id)
    tz = clinic_tz()
    current = datetime(day.year, day.month, day.day, fh, fm, tzinfo=tz).astimezone(timezone.utc)
    end_of_day = datetime(day.year, day.month, day.day, th, tm, tzinfo=tz).astimezone(timezone.utc)
    booked = await _booked_intervals(db, doctor_id, current, end_of_day)
    slots = []
    while current < end_of_day:
        slot_end = current + timedelta(minutes=SLOT_MINUTES)
        if not _overlaps(current, slot_end, booked):
            slots.append(current)
        current = slot_end
    return slots


async def alternative_slots(
    db: AsyncSession, doctor_id: uuid.UUID, around: datetime, limit: int = 3, days_ahead: int = 7,
) -> list[str]:
    """Next free slots at or after `around` (never in the past)."""
    around = max(as_utc(around), datetime.now(timezone.utc))
    found: list[str] = []
    for offset in range(days_ahead + 1):
        day = (around.astimezone(clinic_tz()) + timedelta(days=offset)).date()
        for slot in await available_slots(db, doctor_id, day):
            if slot >= around:
                found.append(slot.isoformat())
                if len(found) >= limit:
                    return found
    return found
