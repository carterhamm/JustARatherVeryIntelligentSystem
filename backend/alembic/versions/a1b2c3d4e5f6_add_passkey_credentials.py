"""Add passkey_credentials table and make hashed_password nullable.

Revision ID: a1b2c3d4e5f6
Revises: 6d04365ad32b
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "a1b2c3d4e5f6"
down_revision = "6d04365ad32b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create passkey_credentials table
    op.create_table(
        "passkey_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_name", sa.String(256), nullable=True),
        sa.Column("transports", postgresql.JSON(), nullable=True),
    )

    # Make hashed_password nullable for passkey-only users
    op.alter_column("users", "hashed_password", existing_type=sa.String(128), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(128), nullable=False)
    op.drop_table("passkey_credentials")
