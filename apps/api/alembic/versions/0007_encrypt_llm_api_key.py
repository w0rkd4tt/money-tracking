"""encrypt llm_provider.api_key at rest (AES-GCM)

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24

Was Text plaintext; becomes LargeBinary (BYTEA) ciphertext. Existing plaintext
values are encrypted in-place using the app's APP_ENCRYPTION_KEY.

downgrade() decrypts back to plaintext — only works if the same encryption key
is available. Otherwise you'll need to wipe api_key values first.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new encrypted column alongside the plaintext one.
    op.add_column(
        "llm_provider",
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=True),
    )

    # 2. Encrypt any existing plaintext rows.
    from money_api.services.crypto import encrypt

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, api_key FROM llm_provider WHERE api_key IS NOT NULL AND api_key != ''")
    ).fetchall()
    for row in rows:
        plain = row.api_key
        if not plain:
            continue
        ciphertext = encrypt(plain)
        conn.execute(
            sa.text("UPDATE llm_provider SET api_key_enc = :c WHERE id = :i"),
            {"c": ciphertext, "i": row.id},
        )

    # 3. Drop old plaintext column, rename encrypted one to api_key.
    op.drop_column("llm_provider", "api_key")
    op.alter_column("llm_provider", "api_key_enc", new_column_name="api_key")


def downgrade() -> None:
    op.add_column(
        "llm_provider",
        sa.Column("api_key_plain", sa.Text(), nullable=True),
    )
    from money_api.services.crypto import decrypt

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, api_key FROM llm_provider WHERE api_key IS NOT NULL")
    ).fetchall()
    for row in rows:
        blob = row.api_key
        if not blob:
            continue
        plain = decrypt(bytes(blob))
        conn.execute(
            sa.text("UPDATE llm_provider SET api_key_plain = :p WHERE id = :i"),
            {"p": plain, "i": row.id},
        )

    op.drop_column("llm_provider", "api_key")
    op.alter_column("llm_provider", "api_key_plain", new_column_name="api_key")
