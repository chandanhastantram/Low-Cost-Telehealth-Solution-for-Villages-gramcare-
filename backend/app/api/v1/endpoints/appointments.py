"""
GramCare – Appointment endpoints
POST   /api/v1/appointments          – book appointment (offline-safe)
GET    /api/v1/appointments          – list (filtered by role)
GET    /api/v1/appointments/{id}     – get one
PATCH  /api/v1/appointments/{id}     – update status / reschedule
GET    /api/v1/appointments/slots    – available doctor slots
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CHWOrAbove, CurrentUser, get_db
from app.models.models import (
    Appointment,
    AppointmentStatus,
    DoctorProfile,
    SyncStatus,
    UserRole,
)
from app.schemas.schemas import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    OKResponse,
    PaginatedResponse,
)
from app.utils.audit import log_action
from app.utils.sync import bump_version

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.get("/slots")
async def get_available_slots(
    doctor_id: uuid.UUID,
    date: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
):
    """
    Return available 15-minute slots for a doctor on a given date.
    Slots already booked are excluded.
    """
    # Parse date
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD.")

    # Get doctor profile for availability hours
    result = await db.execute(
        select(DoctorProfile).where(DoctorProfile.user_id == doctor_id)
    )
    doc = result.scalar_one_or_none()
    avail_from = "09:00"
    avail_to = "17:00"
    if doc:
        avail_from = doc.available_from or avail_from
        avail_to = doc.available_to or avail_to

    # Generate all 15-min slots
    start_h, start_m = map(int, avail_from.split(":"))
    end_h, end_m = map(int, avail_to.split(":"))
    all_slots = []
    current = datetime(
        target_date.year, target_date.month, target_date.day, start_h, start_m, tzinfo=timezone.utc
    )
    end_dt = datetime(
        target_date.year, target_date.month, target_date.day, end_h, end_m, tzinfo=timezone.utc
    )
    while current < end_dt:
        all_slots.append(current)
        current += timedelta(minutes=15)

    # Remove booked slots
    booked_result = await db.execute(
        select(Appointment.scheduled_at).where(
            and_(
                Appointment.doctor_id == doctor_id,
                Appointment.status.notin_([AppointmentStatus.cancelled]),
                func.date(Appointment.scheduled_at) == target_date,
            )
        )
    )
    booked = {row[0] for row in booked_result.fetchall()}
    available = [s.isoformat() for s in all_slots if s not in booked]

    return {"doctor_id": str(doctor_id), "date": date, "available_slots": available}


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: AppointmentCreate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """
    Book an appointment. Idempotent via idempotency_key.
    If offline, appointment is stored with status=pending and synced later.
    Slot conflicts detected server-side return 409 with alternative slots.
    """
    # Idempotency check
    if body.idempotency_key:
        result = await db.execute(
            select(Appointment).where(Appointment.idempotency_key == body.idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    # Slot conflict check
    result = await db.execute(
        select(Appointment).where(
            and_(
                Appointment.doctor_id == body.doctor_id,
                Appointment.scheduled_at == body.scheduled_at,
                Appointment.status.notin_([AppointmentStatus.cancelled]),
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot already booked. Please choose another time.",
        )

    # Generate the id up front: SQLAlchemy's Column(default=uuid.uuid4) is
    # only applied on flush, so appointment.id would still be None here if
    # left to the default — which previously produced call_room_name
    # "gramcare-None".
    appointment_id = uuid.uuid4()
    appointment = Appointment(
        id=appointment_id,
        patient_id=body.patient_id,
        doctor_id=body.doctor_id,
        chw_id=current_user.id if current_user.role == UserRole.chw else None,
        facility_id=body.facility_id,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
        consultation_mode=body.consultation_mode,
        notes=body.notes,
        status=AppointmentStatus.confirmed,
        idempotency_key=body.idempotency_key,
        call_room_name=f"gramcare-{appointment_id}",
    )
    appointment.server_version = await bump_version(db, "appointments")
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    await log_action(db, current_user.id, "create", "appointment", str(appointment.id))
    return appointment


@router.get("", response_model=PaginatedResponse)
async def list_appointments(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    status_filter: Optional[AppointmentStatus] = Query(None, alias="status"),
    patient_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    current_user: CurrentUser = None,
    db: AsyncSession = Depends(get_db),
):
    """List appointments scoped by role."""
    query = select(Appointment)

    if current_user.role == UserRole.patient:
        # Patients see only their own
        from app.models.models import PatientProfile
        prof_result = await db.execute(
            select(PatientProfile).where(PatientProfile.user_id == current_user.id)
        )
        prof = prof_result.scalar_one_or_none()
        if prof:
            query = query.where(Appointment.patient_id == prof.id)
    elif current_user.role == UserRole.doctor:
        from app.models.models import DoctorProfile
        prof_result = await db.execute(
            select(DoctorProfile).where(DoctorProfile.user_id == current_user.id)
        )
        prof = prof_result.scalar_one_or_none()
        if prof:
            query = query.where(Appointment.doctor_id == prof.id)
    elif current_user.role == UserRole.chw:
        query = query.where(Appointment.chw_id == current_user.id)

    if status_filter:
        query = query.where(Appointment.status == status_filter)
    if patient_id:
        query = query.where(Appointment.patient_id == patient_id)
    if doctor_id:
        query = query.where(Appointment.doctor_id == doctor_id)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(Appointment.scheduled_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    items = result.scalars().all()

    return PaginatedResponse(
        total=total, page=page, per_page=per_page,
        items=[AppointmentResponse.model_validate(a) for a in items],
    )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return appt


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentUpdate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    for field, value in body.model_dump(exclude_none=True, exclude={"idempotency_key"}).items():
        setattr(appt, field, value)

    appt.server_version = await bump_version(db, "appointments")
    await db.commit()
    await db.refresh(appt)
    await log_action(db, current_user.id, "update", "appointment", str(appointment_id))
    return appt
