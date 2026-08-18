"""Add per-device wrapped keys to attachments

Revision ID: f9a8b7c6d5e4
Revises: a4b7c9d2e1f0
Create Date: 2026-08-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a8b7c6d5e4'
down_revision: Union[str, Sequence[str], None] = 'a4b7c9d2e1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'attachments',
        sa.Column(
            'wrapped_keys',
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        'attachments',
        'wrapped_keys',
    )