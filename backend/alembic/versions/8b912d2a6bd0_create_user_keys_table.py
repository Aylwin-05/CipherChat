"""create user keys table

Revision ID: 8b912d2a6bd0
Revises: 426295c3cbd8
Create Date: 2026-07-23 16:45:55.406387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b912d2a6bd0'
down_revision: Union[str, Sequence[str], None] = '426295c3cbd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():

    op.create_table(
        "user_keys",

        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "user_id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "public_key",
            sa.LargeBinary(),
            nullable=False,
        ),

        sa.Column(
            "private_key_encrypted",
            sa.LargeBinary(),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint("user_id"),
    )


def downgrade():

    op.drop_table("user_keys")