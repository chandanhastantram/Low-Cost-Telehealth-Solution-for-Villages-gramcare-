"""
GramCare – Record-level access control (on top of role checks in deps.py)

Rules:
  • admin   – everything
  • doctor  – any patient (doctors consult across facilities); appointments
              only where they are the assigned doctor
  • chw     – patients in their own facility; appointments they booked or
              whose patient is in their facility
  • patient – only their own profile, records and appointments
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Appointment,
    DoctorProfile,
    Encounter,
    PatientProfile,
    User,
    UserRole,
)


def _forbidden(detail: str = "Access denied.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def get_own_patient_profile(db: AsyncSession, user: User) -> Optional[PatientProfile]:
    result = await db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
    return result.scalar_one_or_none()


async def get_own_doctor_profile(db: AsyncSession, user: User) -> Optional[DoctorProfile]:
    result = await db.execute(select(DoctorProfile).where(DoctorProfile.user_id == user.id))
    return result.scalar_one_or_none()


async def can_access_patient(db: AsyncSession, user: User, patient: PatientProfile) -> bool:
    if user.role in (UserRole.admin, UserRole.doctor):
        return True
    if user.role == UserRole.chw:
        return patient.facility_id == user.facility_id
    if user.role == UserRole.patient:
        return patient.user_id == user.id
    return False


async def can_access_appointment(db: AsyncSession, user: User, appt: Appointment) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.doctor:
        doc = await get_own_doctor_profile(db, user)
        return bool(doc and appt.doctor_id == doc.id)
    if user.role == UserRole.chw:
        if appt.chw_id == user.id:
            return True
        patient = await db.get(PatientProfile, appt.patient_id)
        return bool(patient and patient.facility_id == user.facility_id)
    if user.role == UserRole.patient:
        patient = await get_own_patient_profile(db, user)
        return bool(patient and appt.patient_id == patient.id)
    return False


async def load_patient_or_404(db: AsyncSession, user: User, patient_id) -> PatientProfile:
    patient = await db.get(PatientProfile, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    if not await can_access_patient(db, user, patient):
        raise _forbidden()
    return patient


async def load_encounter_or_404(db: AsyncSession, user: User, encounter_id) -> Encounter:
    encounter = await db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found.")
    await load_patient_or_404(db, user, encounter.patient_id)
    return encounter


async def load_appointment_or_404(db: AsyncSession, user: User, appointment_id) -> Appointment:
    appt = await db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if not await can_access_appointment(db, user, appt):
        raise _forbidden("Not authorized for this appointment.")
    return appt
