"""
GramCare – All SQLAlchemy ORM models

Roles:   patient | chw | doctor | admin
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, PyEnum):
    patient = "patient"
    chw = "chw"
    doctor = "doctor"
    admin = "admin"


class AppointmentStatus(str, PyEnum):
    pending = "pending"          # offline-created, not yet confirmed
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"


class ConsultationMode(str, PyEnum):
    live_audio = "live_audio"
    live_video = "live_video"
    store_forward = "store_forward"


class SyncStatus(str, PyEnum):
    pending = "pending"
    synced = "synced"
    conflict = "conflict"
    rejected = "rejected"


class AuditAction(str, PyEnum):
    create = "create"
    read = "read"
    update = "update"
    delete = "delete"
    login = "login"
    logout = "logout"
    sync = "sync"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def uuid_pk():
    return Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )


def now_utc():
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = uuid_pk()
    phone = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.patient)
    language_code = Column(String(10), default="en")   # en | hi | kn | …
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    device_pin_hash = Column(String(255), nullable=True)   # offline PIN
    created_at = now_utc()
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # relationships
    facility = relationship("Facility", back_populates="users")
    patient_profile = relationship("PatientProfile", back_populates="user", uselist=False)
    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False)
    chw_profile = relationship("CHWProfile", back_populates="user", uselist=False)
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all,delete")
    audit_logs = relationship("AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id")

    __table_args__ = (
        Index("ix_users_role_facility", "role", "facility_id"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(512), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = now_utc()

    user = relationship("User", back_populates="refresh_tokens")


# ─── Facility ─────────────────────────────────────────────────────────────────

class Facility(Base):
    __tablename__ = "facilities"

    id = uuid_pk()
    name = Column(String(300), nullable=False)
    district = Column(String(200))
    state = Column(String(200))
    pincode = Column(String(10))
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    created_at = now_utc()

    users = relationship("User", back_populates="facility")
    patients = relationship("PatientProfile", back_populates="facility")


# ─── Patient Profile ──────────────────────────────────────────────────────────

class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    date_of_birth = Column(DateTime(timezone=True))
    gender = Column(String(20))
    abha_id = Column(String(100), nullable=True, unique=True)  # Ayushman Bharat Health Account
    blood_group = Column(String(5))
    allergies = Column(Text)
    chronic_conditions = Column(Text)
    emergency_contact_name = Column(String(200))
    emergency_contact_phone = Column(String(20))
    consent_recorded = Column(Boolean, default=False)
    consent_timestamp = Column(DateTime(timezone=True))
    # Sync fields
    server_version = Column(BigInteger, default=0)
    client_id = Column(String(100))   # device identifier for conflict tracking
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.synced)
    created_at = now_utc()
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="patient_profile")
    facility = relationship("Facility", back_populates="patients")
    encounters = relationship("Encounter", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")


# ─── CHW Profile ──────────────────────────────────────────────────────────────

class CHWProfile(Base):
    __tablename__ = "chw_profiles"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    employee_id = Column(String(100))
    qualification = Column(String(200))
    created_at = now_utc()

    user = relationship("User", back_populates="chw_profile")


# ─── Doctor Profile ───────────────────────────────────────────────────────────

class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    registration_number = Column(String(100))
    specialization = Column(String(200))
    available_from = Column(String(10))   # HH:MM
    available_to = Column(String(10))     # HH:MM
    created_at = now_utc()

    user = relationship("User", back_populates="doctor_profile")
    appointments = relationship("Appointment", back_populates="doctor")


# ─── Encounter (Health Record) ────────────────────────────────────────────────

class Encounter(Base):
    __tablename__ = "encounters"

    id = uuid_pk()
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id"), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    chw_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    encounter_date = Column(DateTime(timezone=True), nullable=False)
    chief_complaint = Column(Text)
    symptoms_json = Column(JSONB)         # icon-based symptom selections
    voice_note_url = Column(String(500))  # S3/MinIO key
    photo_urls = Column(JSONB)            # list of S3/MinIO keys
    consultation_mode = Column(Enum(ConsultationMode))
    # Vitals
    temperature_c = Column(Numeric(4, 1))
    pulse_bpm = Column(Integer)
    spo2_pct = Column(Integer)
    bp_systolic = Column(Integer)
    bp_diastolic = Column(Integer)
    respiratory_rate = Column(Integer)
    weight_kg = Column(Numeric(5, 1))
    height_cm = Column(Numeric(5, 1))
    # Triage
    triage_flags = Column(JSONB)          # rule-based red-flag output
    # Sync
    server_version = Column(BigInteger, default=0)
    idempotency_key = Column(String(200), unique=True, nullable=True)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.synced)
    created_at = now_utc()

    patient = relationship("PatientProfile", back_populates="encounters")
    appointment = relationship("Appointment", back_populates="encounter", uselist=False)
    prescriptions = relationship("Prescription", back_populates="encounter")
    attachments = relationship("MediaAttachment", back_populates="encounter")


# ─── Appointment ──────────────────────────────────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"

    id = uuid_pk()
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctor_profiles.id"), nullable=False)
    chw_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=15)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.pending, nullable=False)
    consultation_mode = Column(Enum(ConsultationMode), default=ConsultationMode.live_audio)
    notes = Column(Text)
    call_room_name = Column(String(300))   # P2P WebRTC signaling room (Socket.IO)
    # Sync
    server_version = Column(BigInteger, default=0)
    idempotency_key = Column(String(200), unique=True, nullable=True)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.synced)
    created_at = now_utc()
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("PatientProfile", back_populates="appointments")
    doctor = relationship("DoctorProfile", back_populates="appointments")
    encounter = relationship("Encounter", back_populates="appointment", uselist=False)
    messages = relationship("ChatMessage", back_populates="appointment", cascade="all,delete-orphan")

    __table_args__ = (
        # Prevent double-booking a doctor at same slot
        UniqueConstraint("doctor_id", "scheduled_at", name="uq_doctor_slot"),
        Index("ix_appt_patient_status", "patient_id", "status"),
        Index("ix_appt_doctor_scheduled", "doctor_id", "scheduled_at"),
    )


# ─── Prescription ─────────────────────────────────────────────────────────────

class Prescription(Base):
    __tablename__ = "prescriptions"

    id = uuid_pk()
    encounter_id = Column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    medications = Column(JSONB, nullable=False)   # [{name, dose, frequency, duration}]
    advice = Column(Text)
    follow_up_date = Column(DateTime(timezone=True))
    referral_facility = Column(String(300))
    pdf_url = Column(String(500))   # generated PDF stored in MinIO
    server_version = Column(BigInteger, default=0)
    idempotency_key = Column(String(200), unique=True, nullable=True)
    created_at = now_utc()

    encounter = relationship("Encounter", back_populates="prescriptions")


# ─── Media Attachment ─────────────────────────────────────────────────────────

class MediaAttachment(Base):
    __tablename__ = "media_attachments"

    id = uuid_pk()
    encounter_id = Column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    file_key = Column(String(500), nullable=False)   # MinIO object key
    file_type = Column(String(50))                    # image/jpeg, audio/ogg, application/pdf
    file_size_bytes = Column(BigInteger)
    checksum_sha256 = Column(String(64))
    upload_completed = Column(Boolean, default=False)
    created_at = now_utc()

    encounter = relationship("Encounter", back_populates="attachments")


# ─── Store-and-Forward Case Bundle ───────────────────────────────────────────

class StoreForwardBundle(Base):
    __tablename__ = "store_forward_bundles"

    id = uuid_pk()
    encounter_id = Column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id"), nullable=False)
    chw_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payload_json = Column(JSONB, nullable=False)   # structured complaint + vitals
    voice_note_url = Column(String(500))
    photo_urls = Column(JSONB)
    status = Column(String(50), default="queued")   # queued | reviewed | replied
    doctor_response = Column(Text)
    prescription_id = Column(UUID(as_uuid=True), ForeignKey("prescriptions.id"), nullable=True)
    idempotency_key = Column(String(200), unique=True, nullable=True)
    created_at = now_utc()
    reviewed_at = Column(DateTime(timezone=True))


# ─── Chat Message (real-time, Socket.IO) ─────────────────────────────────────

class ChatMessage(Base):
    """
    In-consultation text chat, tied to an appointment. Delivered live over
    Socket.IO and persisted here so it's visible in sync/pull and in the
    store-and-forward-style history if a participant was offline.
    """
    __tablename__ = "chat_messages"

    id = uuid_pk()
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    idempotency_key = Column(String(200), unique=True, nullable=True)
    created_at = now_utc()

    appointment = relationship("Appointment", back_populates="messages")
    sender = relationship("User")

    __table_args__ = (
        Index("ix_chat_appointment_created", "appointment_id", "created_at"),
    )


# ─── Sync Change Log ──────────────────────────────────────────────────────────

class SyncChangeLog(Base):
    """Append-only log used by the delta-sync endpoint."""
    __tablename__ = "sync_change_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_name = Column(String(100), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    operation = Column(String(20), nullable=False)   # insert | update | delete
    payload = Column(JSONB, nullable=False)
    version = Column(BigInteger, nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    idempotency_key = Column(String(200), nullable=True)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)

    __table_args__ = (
        Index("ix_sync_change_table_version", "table_name", "version"),
        Index("ix_sync_change_facility_version", "facility_id", "version"),
    )


# ─── Audit Log ───────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Append-only; never updated or deleted."""
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(Enum(AuditAction), nullable=False)
    resource_type = Column(String(100))
    resource_id = Column(String(200))
    details = Column(JSONB)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor = relationship("User", back_populates="audit_logs", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_audit_actor_created", "actor_id", "created_at"),
        Index("ix_audit_resource", "resource_type", "resource_id"),
    )


# ─── Triage Rules ─────────────────────────────────────────────────────────────

class TriageRule(Base):
    __tablename__ = "triage_rules"

    id = uuid_pk()
    name = Column(String(200), nullable=False)
    description = Column(Text)
    condition_json = Column(JSONB, nullable=False)   # rule definition
    severity = Column(String(20))                    # red | orange | yellow
    advice = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = now_utc()


# ─── OTP Store ────────────────────────────────────────────────────────────────

class OTPRecord(Base):
    __tablename__ = "otp_records"

    id = uuid_pk()
    phone = Column(String(20), nullable=False, index=True)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified = Column(Boolean, default=False)
    attempt_count = Column(Integer, default=0)
    created_at = now_utc()
