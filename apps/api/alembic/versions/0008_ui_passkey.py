"""ui_passkey table for WebAuthn passkey credentials

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25

One row per registered authenticator (Touch ID / Face ID / Windows Hello /
security key). Users may enrol multiple devices; authentication picks whichever
credential the browser surfaces.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ui_passkey",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("transports", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_ui_passkey_credential_id",
        "ui_passkey",
        ["credential_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_ui_passkey_credential_id", table_name="ui_passkey")
    op.drop_table("ui_passkey")
