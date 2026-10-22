"""
GramCare – Pydantic schemas (request / response models)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from app.models.models import (
    AppointmentStatus,
    ConsultationMode,
    SyncStatus,
    UserRole,
)


# ─── Shared ───────────────────────────────────────────────────────────────────

class OKResponse(BaseModel):
    ok: bool = True
    message: str = "success"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class OTPRequestSchema(BaseModel):
    phone: str = Field(..., examples=["+919876543210"])
    name: Optional[str] = None   # required only for new user registration


class OTPVerifySchema(BaseModel):
    phone: str
    otp: str
    role: Optional[UserRole] = UserRole.patient


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    name: str


class RefreshTokenSchema(BaseModel):
    refresh_token: str


# ─── User ─────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    phone: str
    name: str
    role: UserRole
    language_code: str = "en"
    facility_id: Optional[uuid.UUID] = None


class UserCreate(UserBase):
    pass


SUPPORTED_LANGUAGES = {"en", "hi", "kn", "ta", "te", "mr", "bn"}


class UserUpdate(BaseModel):
    """Self-service fields only; role/facility changes go through the admin endpoint."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    language_code: Optional[str] = None

    @field_validator("language_code")
    @classmethod
    def _known_language(cls, v):
        if v is not None and v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language_code must be one of {sorted(SUPPORTED_LANGUAGES)}")
        return v


class AdminUserUpdate(UserUpdate):
    role: Optional[UserRole] = None
    facility_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    has_offline_pin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class PinSetRequest(BaseModel):
    pin: str = Field(..., pattern=r"^\d{4,6}$", description="4–6 digit offline unlock PIN")


class PinVerifyRequest(BaseModel):
    pin: str


class PinVerifyResponse(BaseModel):
    valid: bool
    attempts_remaining: int


# ─── Facility ─────────────────────────────────────────────────────────────────

class FacilityCreate(BaseModel):
    name: str
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class FacilityResponse(FacilityCreate):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Doctor / CHW onboarding (admin) ──────────────────────────────────────────

class DoctorProfileCreate(BaseModel):
    user_id: uuid.UUID
    registration_number: Optional[str] = None
    specialization: Optional[str] = None
    available_from: str = "09:00"
    available_to: str = "17:00"


class DoctorProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    registration_number: Optional[str]
    specialization: Optional[str]
    available_from: Optional[str]
    available_to: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CHWProfileCreate(BaseModel):
    user_id: uuid.UUID
    facility_id: Optional[uuid.UUID] = None   # CHWs only see their facility's patients
    employee_id: Optional[str] = None
    qualification: Optional[str] = None


class CHWProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    employee_id: Optional[str]
    qualification: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Patient Profile ──────────────────────────────────────────────────────────

class PatientProfileCreate(BaseModel):
    user_id: uuid.UUID
    facility_id: Optional[uuid.UUID] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    abha_id: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    consent_recorded: bool = False
    # Sync
    client_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class PatientProfileUpdate(BaseModel):
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    idempotency_key: Optional[str] = None


class PatientProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    facility_id: Optional[uuid.UUID]
    date_of_birth: Optional[datetime]
    gender: Optional[str]
    abha_id: Optional[str]
    blood_group: Optional[str]
    allergies: Optional[str]
    chronic_conditions: Optional[str]
    consent_recorded: bool
    server_version: int
    sync_status: SyncStatus
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── Vitals ───────────────────────────────────────────────────────────────────

class VitalsSchema(BaseModel):
    temperature_c: Optional[float] = None
    pulse_bpm: Optional[int] = None
    spo2_pct: Optional[int] = None
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    respiratory_rate: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None


# ─── Encounter ────────────────────────────────────────────────────────────────

class EncounterCreate(BaseModel):
    patient_id: uuid.UUID
    appointment_id: Optional[uuid.UUID] = None
    encounter_date: datetime
    chief_complaint: Optional[str] = None
    symptoms_json: Optional[Dict[str, Any]] = None
    consultation_mode: Optional[ConsultationMode] = ConsultationMode.live_audio
    vitals: Optional[VitalsSchema] = None
    triage_flags: Optional[Dict[str, Any]] = None
    idempotency_key: Optional[str] = None


class EncounterResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    appointment_id: Optional[uuid.UUID]
    chw_id: Optional[uuid.UUID]
    doctor_id: Optional[uuid.UUID]
    encounter_date: datetime
    chief_complaint: Optional[str]
    symptoms_json: Optional[Dict]
    consultation_mode: Optional[ConsultationMode]
    temperature_c: Optional[float]
    pulse_bpm: Optional[int]
    spo2_pct: Optional[int]
    bp_systolic: Optional[int]
    bp_diastolic: Optional[int]
    triage_flags: Optional[Dict]
    server_version: int
    sync_status: SyncStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Appointment ──────────────────────────────────────────────────────────────

class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: Optional[uuid.UUID] = None
    scheduled_at: datetime
    duration_minutes: int = 15
    consultation_mode: ConsultationMode = ConsultationMode.live_audio
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None


class AppointmentUpdate(BaseModel):
    status: Optional[AppointmentStatus] = None
    scheduled_at: Optional[datetime] = None
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    chw_id: Optional[uuid.UUID]
    facility_id: Optional[uuid.UUID]
    scheduled_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    consultation_mode: ConsultationMode
    notes: Optional[str]
    call_room_name: Optional[str]
    server_version: int
    sync_status: SyncStatus
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── Prescription ─────────────────────────────────────────────────────────────

class MedicationItem(BaseModel):
    name: str
    dose: str
    frequency: str
    duration: str
    instructions: Optional[str] = None


class PrescriptionCreate(BaseModel):
    # Not required: the endpoint is POST /encounters/{encounter_id}/prescriptions
    # and always uses the path param, never this field.
    encounter_id: Optional[uuid.UUID] = None
    medications: List[MedicationItem]
    advice: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    referral_facility: Optional[str] = None
    idempotency_key: Optional[str] = None


class PrescriptionResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    doctor_id: uuid.UUID
    issued_at: datetime
    medications: List[Dict]
    advice: Optional[str]
    follow_up_date: Optional[datetime]
    referral_facility: Optional[str]
    pdf_url: Optional[str]
    server_version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Store-and-Forward ────────────────────────────────────────────────────────

class StoreForwardCreate(BaseModel):
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    payload_json: Dict[str, Any]
    idempotency_key: Optional[str] = None


class StoreForwardRespond(BaseModel):
    response_text: str = Field(..., min_length=1)
    # Optional: issue a prescription on the bundle's encounter in the same step.
    prescription: Optional[PrescriptionCreate] = None


class StoreForwardResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    chw_id: uuid.UUID
    doctor_id: Optional[uuid.UUID]
    payload_json: Optional[Dict[str, Any]] = None
    voice_note_url: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    status: str
    doctor_response: Optional[str]
    prescription_id: Optional[uuid.UUID] = None
    created_at: datetime
    reviewed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── Sync ─────────────────────────────────────────────────────────────────────

class OutboxEntry(BaseModel):
    operation: str                     # insert | update | delete
    table_name: str
    record_id: str
    payload: Dict[str, Any]
    local_version: int
    idempotency_key: str
    timestamp: datetime


class SyncUploadRequest(BaseModel):
    client_id: str
    facility_id: Optional[str] = None
    checkpoint: int = 0                # last server version client has
    entries: List[OutboxEntry]


class SyncConflict(BaseModel):
    record_id: str
    table_name: str
    server_payload: Dict               # server's current copy of the record
    resolution: str                    # rejected | last_writer_wins
    alternative_slots: List[str] = []  # appointments only


class SyncEntryResult(BaseModel):
    """Per-entry outcome so the client knows which outbox rows to drop."""
    idempotency_key: str
    status: str                        # accepted | rejected | conflict
    reason: Optional[str] = None
    server_version: Optional[int] = None


class SyncUploadResponse(BaseModel):
    accepted: int
    rejected: int
    conflicts: List[SyncConflict]
    results: List[SyncEntryResult] = []
    new_checkpoint: int


class SyncPullResponse(BaseModel):
    changes: List[Dict[str, Any]]
    new_checkpoint: int
    has_more: bool


# ─── Teleconsultation (peer-to-peer WebRTC, signaled over Socket.IO) ─────────

class CallRoomRequest(BaseModel):
    appointment_id: uuid.UUID


class CallRoomResponse(BaseModel):
    room_name: str
    ice_servers: List[Dict]
    socketio_path: str = "/socket.io"


# ─── Chat (real-time messaging over Socket.IO) ───────────────────────────────

class ChatMessageCreate(BaseModel):
    appointment_id: uuid.UUID
    body: str = Field(..., min_length=1, max_length=4000)
    idempotency_key: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    appointment_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Triage ───────────────────────────────────────────────────────────────────

class TriageEvalRequest(BaseModel):
    symptoms: Dict[str, Any]
    vitals: Optional[VitalsSchema] = None


class TriageFlag(BaseModel):
    rule_name: str
    severity: str
    advice: str


class TriageEvalResponse(BaseModel):
    flags: List[TriageFlag]
    urgent: bool
    summary: str


# ─── Media Upload ─────────────────────────────────────────────────────────────

class PresignedUploadRequest(BaseModel):
    encounter_id: uuid.UUID
    file_name: str
    content_type: str
    file_size_bytes: int


class PresignedUploadResponse(BaseModel):
    upload_url: str
    file_key: str
    attachment_id: uuid.UUID
    expires_in_seconds: int


# ─── Pagination ───────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[Any]
