"""Add attachment type

Revision ID: 426295c3cbd8
Revises: b4b8ef7b83ba
Create Date: 2026-07-22 22:46:40.776253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '426295c3cbd8'
down_revision: Union[str, Sequence[str], None] = 'b4b8ef7b83ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():

    op.add_column(
        "attachments",
        sa.Column(
            "attachment_type",
            sa.String(length=30),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE attachments
        SET attachment_type='document'
        """
    )

    op.alter_column(
        "attachments",
        "attachment_type",
        nullable=False,
    )


def downgrade():

    op.drop_column(
        "attachments",
        "attachment_type",
    )
