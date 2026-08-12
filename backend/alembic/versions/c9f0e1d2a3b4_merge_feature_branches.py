"""merge feature branches (message features / conversation features)

Revision ID: c9f0e1d2a3b4
Revises: a1b2c3d4e5f6, b2c4d6e8f0a2
Create Date: 2026-08-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9f0e1d2a3b4'
down_revision: Union[str, Sequence[str], None] = [
    'a1b2c3d4e5f6',
    'b2c4d6e8f0a2',
]
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    pass


def downgrade():
    pass