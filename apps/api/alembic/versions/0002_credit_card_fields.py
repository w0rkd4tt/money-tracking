"""add credit_limit + statement_close_day to account

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column("credit_limit", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "account",
        sa.Column("statement_close_day", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account", "statement_close_day")
    op.drop_column("account", "credit_limit")
