"""ui unlock: passphrase + recovery key + session

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-23

UI-only gate (not full API auth). A single passphrase unlocks the web UI;
a recovery key (shown once at setup) can reset a forgotten passphrase.
Backups of the DB stay usable — passphrase/recovery hashes are rows like any
other, not keys for data encryption.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ui_credential",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("passphrase_hash", sa.String(255), nullable=False),
        sa.Column("recovery_key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ui_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_agent", sa.String(255), nullable=True),
    )
    op.create_index("ix_ui_session_hash", "ui_session", ["token_hash"])
    op.create_index("ix_ui_session_expires", "ui_session", ["expires_at"])


def downgrade() -> None:
    op.drop_table("ui_session")
    op.drop_table("ui_credential")
