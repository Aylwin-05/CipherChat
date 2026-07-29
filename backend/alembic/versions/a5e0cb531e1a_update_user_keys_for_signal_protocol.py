"""update user keys for signal protocol

Revision ID: a5e0cb531e1a
Revises: 5aad8dd25c18
Create Date: 2026-07-30 00:53:58.934213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5e0cb531e1a'
down_revision: Union[str, Sequence[str], None] = '5aad8dd25c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ==========================================================
    # User Keys
    # ==========================================================

    op.add_column(
        "user_keys",
        sa.Column(
            "signed_prekey",
            sa.String(),
            nullable=True,
        ),
    )

    op.add_column(
        "user_keys",
        sa.Column(
            "signed_prekey_signature",
            sa.String(),
            nullable=True,
        ),
    )

    op.drop_column(
        "user_keys",
        "private_key_encrypted",
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ==========================================================
    # User Keys
    # ==========================================================

    op.add_column(
        "user_keys",
        sa.Column(
            "private_key_encrypted",
            sa.String(),
            nullable=False,
        ),
    )

    op.drop_column(
        "user_keys",
        "signed_prekey_signature",
    )

    op.drop_column(
        "user_keys",
        "signed_prekey",
    )