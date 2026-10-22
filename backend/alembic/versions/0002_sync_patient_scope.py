"""sync change log: patient scope

Adds sync_change_log.patient_id so a patient's device can pull only its own
records.

Revision ID: 0002_sync_patient_scope
Revises: 0001_initial_schema
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_sync_patient_scope"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sync_change_log",
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patient_profiles.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sync_change_patient_version", "sync_change_log", ["patient_id", "version"]
    )


def downgrade() -> None:
    op.drop_index("ix_sync_change_patient_version", table_name="sync_change_log")
    op.drop_column("sync_change_log", "patient_id")
