"""Add location_history table.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS location_history (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            city VARCHAR(256),
            state VARCHAR(128),
            country VARCHAR(128)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_location_history_user_created
        ON location_history (user_id, created_at)
    """)


def downgrade() -> None:
    op.drop_table("location_history")
