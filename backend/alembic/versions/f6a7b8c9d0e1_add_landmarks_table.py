"""Add landmarks table.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS landmarks (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(256) NOT NULL,
            description TEXT,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            address VARCHAR(512),
            apple_maps_url VARCHAR(1024),
            icon VARCHAR(32) DEFAULT 'pin',
            color VARCHAR(7) DEFAULT '#f0a500'
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_landmarks_user_id
        ON landmarks (user_id)
    """)


def downgrade() -> None:
    op.drop_table("landmarks")
