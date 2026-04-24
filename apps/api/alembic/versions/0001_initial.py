"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("icon", sa.String(50)),
        sa.Column("color", sa.String(20)),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("category.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("icon", sa.String(50)),
        sa.Column("color", sa.String(20)),
        sa.Column("path", sa.String(255), nullable=False, server_default=""),
    )

    op.create_table(
        "merchant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column(
            "default_category_id", sa.Integer(), sa.ForeignKey("category.id", ondelete="SET NULL")
        ),
        sa.Column("aliases", sa.JSON(), nullable=False),
    )

    op.create_table(
        "transfer_group",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column(
            "from_account_id",
            sa.Integer(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "to_account_id",
            sa.Integer(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fee", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("fx_rate", sa.Numeric(18, 6)),
        sa.Column("note", sa.String(500)),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transfer_group_ts", "transfer_group", ["ts"])

    op.create_table(
        "transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id", ondelete="SET NULL")),
        sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchant.id", ondelete="SET NULL")),
        sa.Column("merchant_text", sa.String(200)),
        sa.Column("note", sa.String(500)),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("raw_ref", sa.String(255)),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("llm_tags", sa.JSON(), nullable=False),
        sa.Column(
            "transfer_group_id",
            sa.Integer(),
            sa.ForeignKey("transfer_group.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tx_account_ts", "transaction", ["account_id", "ts"])
    op.create_index("ix_tx_category_ts", "transaction", ["category_id", "ts"])
    op.create_index("ix_tx_status_ts", "transaction", ["status", "ts"])
    op.create_index("ix_tx_ts", "transaction", ["ts"])
    op.create_unique_constraint("uq_tx_source_raw_ref", "transaction", ["source", "raw_ref"])

    op.create_table(
        "budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id", ondelete="CASCADE")),
        sa.Column("period", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("limit_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("rollover", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("pattern_type", sa.String(20), nullable=False),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("extractor", sa.JSON(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id", ondelete="SET NULL")),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id", ondelete="SET NULL")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(20), nullable=False, server_default="user"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

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

    op.create_table(
        "chat_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_session_external", "chat_session", ["external_id"])

    op.create_table(
        "chat_message",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transaction.id", ondelete="SET NULL"),
        ),
        sa.Column("ts", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "oauth_credential",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("account_email", sa.String(255), nullable=False, unique=True),
        sa.Column("encrypted_token", sa.LargeBinary(), nullable=False),
        sa.Column("scopes", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "sync_state",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "app_setting",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("default_account_id", sa.Integer()),
        sa.Column("locale", sa.String(10), nullable=False, server_default="vi-VN"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Ho_Chi_Minh"),
        sa.Column("default_currency", sa.String(3), nullable=False, server_default="VND"),
        sa.Column("llm_allow_cloud", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("llm_agent_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "llm_gmail_tool_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("theme", sa.String(20), nullable=False, server_default="system"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "notify_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notify_event", "notify_log", ["event_key"])

    op.create_table(
        "llm_gmail_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("pattern_type", sa.String(20), nullable=False),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "llm_tool_call_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_session.id", ondelete="SET NULL"),
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_name", sa.String(50), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_summary", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("trace_id", sa.String(100)),
    )
    op.create_index("ix_llm_audit_ts", "llm_tool_call_log", ["ts"])
    op.create_index("ix_llm_audit_session", "llm_tool_call_log", ["session_id"])
    op.create_index("ix_llm_audit_tool", "llm_tool_call_log", ["tool_name"])

    op.create_table(
        "llm_tool_search_cache",
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("chat_session.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("message_id", sa.String(255), primary_key=True),
        sa.Column("seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_llm_cache_expires", "llm_tool_search_cache", ["expires_at"])


def downgrade() -> None:
    for t in [
        "llm_tool_search_cache",
        "llm_tool_call_log",
        "llm_gmail_policy",
        "notify_log",
        "app_setting",
        "sync_state",
        "oauth_credential",
        "chat_message",
        "chat_session",
        "transaction_tag",
        "tag",
        "rule",
        "budget",
        "transaction",
        "transfer_group",
        "merchant",
        "category",
        "account",
    ]:
        op.drop_table(t)
