"""Add token_hash column to sessions for SHA-256 hashed token lookup.

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "j0e1f2g3h4i5"
down_revision = "i9d0e1f2g3h4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add token_hash column (nullable during transition — existing rows lack it)
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS token_hash VARCHAR(128)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_sessions_token_hash
        ON sessions (token_hash)
    """)


def downgrade() -> None:
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_column("sessions", "token_hash")
