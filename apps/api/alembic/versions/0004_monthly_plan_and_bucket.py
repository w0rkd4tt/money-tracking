"""monthly plan + allocation buckets

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allocation_bucket",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("icon", sa.String(50)),
        sa.Column("color", sa.String(20)),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "bucket_category",
        sa.Column(
            "bucket_id",
            sa.Integer(),
            sa.ForeignKey("allocation_bucket.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("category.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_bucket_category_cat", "bucket_category", ["category_id"])

    op.create_table(
        "monthly_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("month", sa.Date(), nullable=False, unique=True),
        sa.Column("expected_income", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("strategy", sa.String(20), nullable=False, server_default="soft"),
        sa.Column(
            "carry_over_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("note", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "plan_allocation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "monthly_plan_id",
            sa.Integer(),
            sa.ForeignKey("monthly_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bucket_id",
            sa.Integer(),
            sa.ForeignKey("allocation_bucket.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("method", sa.String(10), nullable=False, server_default="amount"),
        sa.Column("value", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("rollover", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.String(255)),
    )
    op.create_unique_constraint(
        "uq_plan_bucket", "plan_allocation", ["monthly_plan_id", "bucket_id"]
    )
    op.create_index("ix_plan_alloc_plan", "plan_allocation", ["monthly_plan_id"])


def downgrade() -> None:
    op.drop_table("plan_allocation")
    op.drop_table("monthly_plan")
    op.drop_table("bucket_category")
    op.drop_table("allocation_bucket")
