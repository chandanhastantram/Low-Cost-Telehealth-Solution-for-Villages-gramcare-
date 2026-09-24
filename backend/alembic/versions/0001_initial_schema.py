"""initial schema

Hand-written to mirror app/models/models.py exactly (no live Postgres was
available to autogenerate against). Table/column order matches the model
file; enum type names match SQLAlchemy's default naming for
Column(Enum(SomePyEnum)) so future `alembic revision --autogenerate` runs
produce minimal diffs.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Extensions + sync sequence (mirrors scripts/init.sql) ─────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute("CREATE SEQUENCE IF NOT EXISTS sync_version_seq START 1 INCREMENT 1")

    # ── Enum types ──────────────────────────────────────────────────────────
    # Created via raw SQL (not ENUM(...).create()) because SQLAlchemy also
    # tries to auto-create an enum the first time it's used in a
    # create_table() column, which double-creates it and errors even with
    # checkfirst=True in some async-driver setups. Every ENUM(...) instance
    # used below passes create_type=False so table creation never re-attempts it.
    op.execute("CREATE TYPE userrole AS ENUM ('patient', 'chw', 'doctor', 'admin')")
    op.execute(
        "CREATE TYPE appointmentstatus AS ENUM "
        "('pending', 'confirmed', 'cancelled', 'completed', 'no_show')"
    )
    op.execute(
        "CREATE TYPE consultationmode AS ENUM "
        "('live_audio', 'live_video', 'store_forward')"
    )
    op.execute(
        "CREATE TYPE syncstatus AS ENUM ('pending', 'synced', 'conflict', 'rejected')"
    )
    op.execute(
        "CREATE TYPE auditaction AS ENUM "
        "('create', 'read', 'update', 'delete', 'login', 'logout', 'sync')"
    )

    def _enum(name: str, *values: str) -> postgresql.ENUM:
        return postgresql.ENUM(*values, name=name, create_type=False)

    user_role = _enum("userrole", "patient", "chw", "doctor", "admin")
    appointment_status = _enum(
        "appointmentstatus", "pending", "confirmed", "cancelled", "completed", "no_show"
    )
    consultation_mode_a = _enum("consultationmode", "live_audio", "live_video", "store_forward")
    consultation_mode_b = _enum("consultationmode", "live_audio", "live_video", "store_forward")
    sync_status_a = _enum("syncstatus", "pending", "synced", "conflict", "rejected")
    sync_status_b = _enum("syncstatus", "pending", "synced", "conflict", "rejected")
    sync_status_c = _enum("syncstatus", "pending", "synced", "conflict", "rejected")
    audit_action = _enum(
        "auditaction", "create", "read", "update", "delete", "login", "logout", "sync"
    )

    # ── facilities ──────────────────────────────────────────────────────────
    op.create_table(
        "facilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("district", sa.String(200)),
        sa.Column("state", sa.String(200)),
        sa.Column("pincode", sa.String(10)),
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── users ───────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="patient"),
        sa.Column("language_code", sa.String(10), server_default="en"),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("device_pin_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_users_phone", "users", ["phone"])
    op.create_index("ix_users_role_facility", "users", ["role", "facility_id"])

    # ── refresh_tokens ──────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(512), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── patient_profiles ────────────────────────────────────────────────────
    op.create_table(
        "patient_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("date_of_birth", sa.DateTime(timezone=True)),
        sa.Column("gender", sa.String(20)),
        sa.Column("abha_id", sa.String(100), nullable=True, unique=True),
        sa.Column("blood_group", sa.String(5)),
        sa.Column("allergies", sa.Text),
        sa.Column("chronic_conditions", sa.Text),
        sa.Column("emergency_contact_name", sa.String(200)),
        sa.Column("emergency_contact_phone", sa.String(20)),
        sa.Column("consent_recorded", sa.Boolean, server_default=sa.false()),
        sa.Column("consent_timestamp", sa.DateTime(timezone=True)),
        sa.Column("server_version", sa.BigInteger, server_default="0"),
        sa.Column("client_id", sa.String(100)),
        sa.Column("sync_status", sync_status_a, server_default="synced"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── chw_profiles ────────────────────────────────────────────────────────
    op.create_table(
        "chw_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("employee_id", sa.String(100)),
        sa.Column("qualification", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── doctor_profiles ─────────────────────────────────────────────────────
    op.create_table(
        "doctor_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("registration_number", sa.String(100)),
        sa.Column("specialization", sa.String(200)),
        sa.Column("available_from", sa.String(10)),
        sa.Column("available_to", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── appointments ────────────────────────────────────────────────────────
    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctor_profiles.id"), nullable=False),
        sa.Column("chw_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, server_default="15"),
        sa.Column("status", appointment_status, nullable=False, server_default="pending"),
        sa.Column("consultation_mode", consultation_mode_a, server_default="live_audio"),
        sa.Column("notes", sa.Text),
        sa.Column("call_room_name", sa.String(300)),
        sa.Column("server_version", sa.BigInteger, server_default="0"),
        sa.Column("idempotency_key", sa.String(200), unique=True, nullable=True),
        sa.Column("sync_status", sync_status_b, server_default="synced"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint("doctor_id", "scheduled_at", name="uq_doctor_slot"),
    )
    op.create_index("ix_appt_patient_status", "appointments", ["patient_id", "status"])
    op.create_index("ix_appt_doctor_scheduled", "appointments", ["doctor_id", "scheduled_at"])

    # ── encounters ──────────────────────────────────────────────────────────
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("chw_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("encounter_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chief_complaint", sa.Text),
        sa.Column("symptoms_json", postgresql.JSONB),
        sa.Column("voice_note_url", sa.String(500)),
        sa.Column("photo_urls", postgresql.JSONB),
        sa.Column("consultation_mode", consultation_mode_b),
        sa.Column("temperature_c", sa.Numeric(4, 1)),
        sa.Column("pulse_bpm", sa.Integer),
        sa.Column("spo2_pct", sa.Integer),
        sa.Column("bp_systolic", sa.Integer),
        sa.Column("bp_diastolic", sa.Integer),
        sa.Column("respiratory_rate", sa.Integer),
        sa.Column("weight_kg", sa.Numeric(5, 1)),
        sa.Column("height_cm", sa.Numeric(5, 1)),
        sa.Column("triage_flags", postgresql.JSONB),
        sa.Column("server_version", sa.BigInteger, server_default="0"),
        sa.Column("idempotency_key", sa.String(200), unique=True, nullable=True),
        sa.Column("sync_status", sync_status_c, server_default="synced"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── prescriptions ───────────────────────────────────────────────────────
    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("medications", postgresql.JSONB, nullable=False),
        sa.Column("advice", sa.Text),
        sa.Column("follow_up_date", sa.DateTime(timezone=True)),
        sa.Column("referral_facility", sa.String(300)),
        sa.Column("pdf_url", sa.String(500)),
        sa.Column("server_version", sa.BigInteger, server_default="0"),
        sa.Column("idempotency_key", sa.String(200), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── media_attachments ───────────────────────────────────────────────────
    op.create_table(
        "media_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(50)),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("upload_completed", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── store_forward_bundles ───────────────────────────────────────────────
    op.create_table(
        "store_forward_bundles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("chw_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("payload_json", postgresql.JSONB, nullable=False),
        sa.Column("voice_note_url", sa.String(500)),
        sa.Column("photo_urls", postgresql.JSONB),
        sa.Column("status", sa.String(50), server_default="queued"),
        sa.Column("doctor_response", sa.Text),
        sa.Column("prescription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prescriptions.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(200), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )

    # ── chat_messages ───────────────────────────────────────────────────────
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.String(200), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_appointment_created", "chat_messages", ["appointment_id", "created_at"])

    # ── sync_change_log ─────────────────────────────────────────────────────
    op.create_table(
        "sync_change_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.BigInteger, nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=True),
    )
    op.create_index("ix_sync_change_table_version", "sync_change_log", ["table_name", "version"])
    op.create_index("ix_sync_change_facility_version", "sync_change_log", ["facility_id", "version"])

    # ── audit_logs ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", audit_action, nullable=False),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", sa.String(200)),
        sa.Column("details", postgresql.JSONB),
        sa.Column("ip_address", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_actor_created", "audit_logs", ["actor_id", "created_at"])
    op.create_index("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"])

    # ── triage_rules ────────────────────────────────────────────────────────
    op.create_table(
        "triage_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("condition_json", postgresql.JSONB, nullable=False),
        sa.Column("severity", sa.String(20)),
        sa.Column("advice", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── otp_records ─────────────────────────────────────────────────────────
    op.create_table(
        "otp_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("otp_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified", sa.Boolean, server_default=sa.false()),
        sa.Column("attempt_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_otp_records_phone", "otp_records", ["phone"])


def downgrade() -> None:
    op.drop_table("otp_records")
    op.drop_table("triage_rules")
    op.drop_table("audit_logs")
    op.drop_table("sync_change_log")
    op.drop_table("chat_messages")
    op.drop_table("store_forward_bundles")
    op.drop_table("media_attachments")
    op.drop_table("prescriptions")
    op.drop_table("encounters")
    op.drop_table("appointments")
    op.drop_table("doctor_profiles")
    op.drop_table("chw_profiles")
    op.drop_table("patient_profiles")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("facilities")

    bind = op.get_bind()
    for type_name in (
        "auditaction",
        "syncstatus",
        "consultationmode",
        "appointmentstatus",
        "userrole",
    ):
        postgresql.ENUM(name=type_name).drop(bind, checkfirst=True)

    op.execute("DROP SEQUENCE IF EXISTS sync_version_seq")
