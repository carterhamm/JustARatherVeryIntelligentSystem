"""Add composite indexes for sessions, passkeys, and conversations.

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-03-13
"""

from alembic import op

# revision identifiers
revision = "i9d0e1f2g3h4"
down_revision = "h8c9d0e1f2g3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sessions — fast lookup of active sessions per user
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_user_active
        ON sessions (user_id, is_active)
    """)
    # Sessions — cleanup by expiry
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sessions_expires
        ON sessions (expires_at)
    """)
    # Passkey credentials — fast user lookup
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_passkeys_user
        ON passkey_credentials (user_id)
    """)
    # Conversations — archived filter
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_conversations_user_archived
        ON conversations (user_id, is_archived)
    """)


def downgrade() -> None:
    op.drop_index("ix_conversations_user_archived", table_name="conversations")
    op.drop_index("ix_passkeys_user", table_name="passkey_credentials")
    op.drop_index("ix_sessions_expires", table_name="sessions")
    op.drop_index("ix_sessions_user_active", table_name="sessions")
