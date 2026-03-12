"""Add health_samples table.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sample_type", sa.String(64), nullable=False, index=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
    )
    # Composite unique index for deduplication
    op.create_index(
        "ix_health_samples_dedup",
        "health_samples",
        ["user_id", "sample_type", "start_date", "end_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_health_samples_dedup", table_name="health_samples")
    op.drop_table("health_samples")
