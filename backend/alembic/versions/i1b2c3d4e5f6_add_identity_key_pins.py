"""add identity key pin table for safety number pinning

Revision ID: i1b2c3d4e5f6
Revises: o2q4s6u8w0a2
Create Date: 2026-08-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'o2q4s6u8w0a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'identity_key_pins',
        sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_identity_key_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'contact_user_id', name='uq_user_contact_pin'),
    )
    op.create_index(
        'ix_identity_key_pins_user_id',
        'identity_key_pins',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        'ix_identity_key_pins_contact_user_id',
        'identity_key_pins',
        ['contact_user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table('identity_key_pins')