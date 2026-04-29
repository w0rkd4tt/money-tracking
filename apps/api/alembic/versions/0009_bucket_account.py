"""bucket_account m:n table — route by account in addition to category

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-28

Lets a bucket aggregate transactions on selected accounts (e.g. all credit
card spend lands in "Trả nợ thẻ TD" regardless of merchant category). Spend
calc routes by account first, falling through to category for accounts that
aren't bucket-mapped — so no double counting.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bucket_account",
        sa.Column(
            "bucket_id",
            sa.Integer(),
            sa.ForeignKey("allocation_bucket.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_bucket_account_account",
        "bucket_account",
        ["account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bucket_account_account", table_name="bucket_account")
    op.drop_table("bucket_account")
