"""drop tag + transaction_tag tables

Tags are redundant with category for this single-user app. Dashboard already
groups by category. Removing to simplify the data model.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("transaction_tag")
    op.drop_table("tag")


def downgrade() -> None:
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
    )
    op.create_table(
        "transaction_tag",
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transaction.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("tag.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
