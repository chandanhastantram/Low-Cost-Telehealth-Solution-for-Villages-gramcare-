"""
GramCare – Appointment endpoints
POST   /api/v1/appointments          – book appointment (offline-safe)
GET    /api/v1/appointments          – list (filtered by role)
GET    /api/v1/appointments/{id}     – get one
PATCH  /api/v1/appointments/{id}     – update status / reschedule
GET    /api/v1/appointments/slots    – available doctor slots
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import (
    get_own_doctor_profile,
    get_own_patient_profile,
    load_appointment_or_404,
    load_patient_or_404,
)
from app.core.deps import CHWOrAbove, CurrentUser, get_db
from app.models.models import (
    Appointment,
    AppointmentStatus,
    DoctorProfile,
    PatientProfile,
    UserRole,
)
from app.schemas.schemas import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    PaginatedResponse,
)
from app.services.scheduling import alternative_slots, available_slots, is_slot_free
from app.utils.audit import log_action
from app.utils.sync import record_change

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def slot_conflict_response(alternatives: list[str]) -> JSONResponse:
    """409 with the next free slots, so the CHW can rebook in one tap."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Slot already booked. Please choose another time.",
            "alternative_slots": alternatives,
        },
    )


@router.get("/slots")
async def get_available_slots(
    doctor_id: uuid.UUID,
    current_user: CurrentUser,
    date: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return available 15-minute slots for a doctor (doctor_profiles.id, as
    listed by GET /doctors) on a given date. Booked/overlapping slots are
    excluded.
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD.")

    slots = await available_slots(db, doctor_id, target_date)
    return {
        "doctor_id": str(doctor_id),
        "date": date,
        "available_slots": [s.isoformat() for s in slots],
    }


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: AppointmentCreate,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """
    Book an appointment. Idempotent via idempotency_key.
    Slot conflicts return 409 with `alternative_slots`.
    """
    if body.idempotency_key:
        result = await db.execute(
            select(Appointment).where(Appointment.idempotency_key == body.idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    patient = await load_patient_or_404(db, current_user, body.patient_id)
    if not await db.get(DoctorProfile, body.doctor_id):
        raise HTTPException(status_code=404, detail="Doctor not found.")

    if not await is_slot_free(db, body.doctor_id, body.scheduled_at, body.duration_minutes):
        return slot_conflict_response(
            await alternative_slots(db, body.doctor_id, body.scheduled_at)
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
        facility_id=body.facility_id or patient.facility_id,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
        consultation_mode=body.consultation_mode,
        notes=body.notes,
        status=AppointmentStatus.confirmed,
        idempotency_key=body.idempotency_key,
        call_room_name=f"gramcare-{appointment_id}",
    )
    db.add(appointment)
    await record_change(db, "appointments", appointment, "insert", current_user.id, body.idempotency_key)
    await log_action(db, current_user.id, "create", "appointment", str(appointment.id))
    await db.commit()
    await db.refresh(appointment)
    return appointment


@router.get("", response_model=PaginatedResponse)
async def list_appointments(
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    status_filter: Optional[AppointmentStatus] = Query(None, alias="status"),
    patient_id: Optional[uuid.UUID] = None,
    doctor_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """List appointments scoped by role."""
    query = select(Appointment)

    if current_user.role == UserRole.patient:
        prof = await get_own_patient_profile(db, current_user)
        query = query.where(Appointment.patient_id == (prof.id if prof else None))
    elif current_user.role == UserRole.doctor:
        prof = await get_own_doctor_profile(db, current_user)
        query = query.where(Appointment.doctor_id == (prof.id if prof else None))
    elif current_user.role == UserRole.chw:
        facility_patients = select(PatientProfile.id).where(
            PatientProfile.facility_id == current_user.facility_id
        )
        query = query.where(
            (Appointment.chw_id == current_user.id) | Appointment.patient_id.in_(facility_patients)
        )

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
    return await load_appointment_or_404(db, current_user, appointment_id)


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Staff may change status, time and notes. A patient may only cancel
    their own appointment.
    """
    appt = await load_appointment_or_404(db, current_user, appointment_id)
    changes = body.model_dump(exclude_none=True, exclude={"idempotency_key"})

    if current_user.role == UserRole.patient and changes != {"status": AppointmentStatus.cancelled}:
        raise HTTPException(status_code=403, detail="Patients may only cancel appointments.")

    new_time = changes.get("scheduled_at")
    if new_time and not await is_slot_free(
        db, appt.doctor_id, new_time, appt.duration_minutes, exclude_id=appt.id
    ):
        return slot_conflict_response(await alternative_slots(db, appt.doctor_id, new_time))

    for field, value in changes.items():
        setattr(appt, field, value)

    await record_change(db, "appointments", appt, "update", current_user.id)
    await log_action(db, current_user.id, "update", "appointment", str(appointment_id), _json(changes))
    await db.commit()
    await db.refresh(appt)
    return appt


def _json(changes: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, datetime) else getattr(v, "value", v)
        for k, v in changes.items()
    }
