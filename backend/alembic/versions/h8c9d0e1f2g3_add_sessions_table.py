"""Add sessions table for login tracking.

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "h8c9d0e1f2g3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_token VARCHAR(64) NOT NULL UNIQUE,
            ip_address VARCHAR(45),
            user_agent VARCHAR(512),
            device_type VARCHAR(32),
            location_city VARCHAR(128),
            location_country VARCHAR(64),
            signed_in_at TIMESTAMPTZ NOT NULL,
            last_active_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            revoked_at TIMESTAMPTZ,
            login_method VARCHAR(32)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_user_id
        ON sessions (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_session_token
        ON sessions (session_token)
    """)


def downgrade() -> None:
    op.drop_table("sessions")
