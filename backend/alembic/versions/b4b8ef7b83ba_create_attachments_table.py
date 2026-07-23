"""Create attachments table

Revision ID: b4b8ef7b83ba
Revises: 253eacc4fae4
Create Date: 2026-07-22 22:41:30.042260

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4b8ef7b83ba"
down_revision: Union[str, Sequence[str], None] = "253eacc4fae4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:

    op.create_table(
        "attachments",

        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "message_id",
            sa.UUID(),
            nullable=False,
        ),

        sa.Column(
            "original_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "mime_type",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "extension",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "size",
            sa.BigInteger(),
            nullable=False,
        ),

        sa.Column(
            "storage_path",
            sa.String(length=500),
            nullable=False,
        ),

        sa.Column(
            "thumbnail_path",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "width",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "height",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "duration",
            sa.Float(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.UniqueConstraint(
            "filename",
        ),
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:

    op.drop_table("attachments")