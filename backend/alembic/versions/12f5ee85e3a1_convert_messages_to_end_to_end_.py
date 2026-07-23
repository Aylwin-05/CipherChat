"""convert messages to end-to-end encryption

Revision ID: 12f5ee85e3a1
Revises: 8b912d2a6bd0
Create Date: 2026-07-23 22:55:19.709410

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '12f5ee85e3a1'
down_revision: Union[str, Sequence[str], None] = '8b912d2a6bd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 1 migration.

    IMPORTANT:
    We DO NOT remove the old plaintext columns yet.

    The backend still uses them.

    This migration only adds the new encrypted
    message fields.
    """

    op.add_column(
        "messages",
        sa.Column(
            "ciphertext",
            sa.LargeBinary(),
            nullable=True,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "encrypted_key",
            sa.LargeBinary(),
            nullable=True,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "nonce",
            sa.LargeBinary(),
            nullable=True,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "crypto_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )


# ==========================================================
# DOWNGRADE
# ==========================================================

def downgrade() -> None:
    """
    Remove only the new encryption columns.
    """

    op.drop_column(
        "messages",
        "crypto_version",
    )

    op.drop_column(
        "messages",
        "nonce",
    )

    op.drop_column(
        "messages",
        "encrypted_key",
    )

    op.drop_column(
        "messages",
        "ciphertext",
    )