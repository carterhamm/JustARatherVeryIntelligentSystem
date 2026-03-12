"""Add focus_sessions table.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "focus_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("category", sa.String(64), nullable=True, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_duration_min", sa.Integer(), nullable=True),
        sa.Column("actual_duration_min", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("distractions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("energy_level", sa.Integer(), nullable=True),
        sa.Column("productivity_rating", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_focus_sessions_user_started",
        "focus_sessions",
        ["user_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_focus_sessions_user_started", table_name="focus_sessions")
    op.drop_table("focus_sessions")
