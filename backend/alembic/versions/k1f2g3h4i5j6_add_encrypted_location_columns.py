"""Add encrypted_lat and encrypted_lng columns to location_history.

Stores Fernet-encrypted latitude/longitude alongside the existing Float
columns for a gradual migration. New writes populate both; reads prefer
the encrypted values when present.

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-03-13
"""

from alembic import op

# revision identifiers
revision = "k1f2g3h4i5j6"
down_revision = "j0e1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE location_history
        ADD COLUMN IF NOT EXISTS encrypted_lat TEXT
    """)
    op.execute("""
        ALTER TABLE location_history
        ADD COLUMN IF NOT EXISTS encrypted_lng TEXT
    """)


def downgrade() -> None:
    op.drop_column("location_history", "encrypted_lng")
    op.drop_column("location_history", "encrypted_lat")
