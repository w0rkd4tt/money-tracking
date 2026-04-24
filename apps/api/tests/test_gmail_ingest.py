"""Test ingest_parsed inserts pending transactions correctly + dedup works."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from money_api.db import SessionLocal
from money_api.ingest.gmail_parser import ParsedTx
from money_api.ingest.gmail_poller import (
    _resolve_category_by_name,
    ingest_parsed,
)
from money_api.models import Category


@pytest.mark.asyncio
async def test_parsed_tx_accepts_category_field():
    """ParsedTx dataclass now has an optional `category` field carrying the
    LLM-extracted path / rule-set leaf name. Defaults to None."""
    p1 = ParsedTx(amount=Decimal("1000"))
    assert p1.category is None
    p2 = ParsedTx(amount=Decimal("1000"), category="Ăn uống > Cafe")
    assert p2.category == "Ăn uống > Cafe"


@pytest.mark.asyncio
async def test_ingest_resolves_category_by_path(seeded):
    """When parsed.category matches an existing category path, the tx gets its id."""
    async with SessionLocal() as session:
        # Add a nested category the LLM might cite
        parent = Category(name="Ăn uống", kind="expense", path="Ăn uống")
        session.add(parent)
        await session.flush()
        cafe = Category(
            name="Cafe", kind="expense", path="Ăn uống > Cafe", parent_id=parent.id
        )
        session.add(cafe)
        await session.commit()

        parsed = ParsedTx(
            amount=Decimal("45000"),
            currency="VND",
            kind="expense",
            merchant="Highland",
            account_hint="VCB",
            ts=datetime(2026, 4, 22, 9, 30),
            rule_name="llm-fallback",
            category="Ăn uống > Cafe",
        )
        tx = await ingest_parsed(session, parsed, message_id="m-cat-1")
        assert tx is not None
        assert tx.category_id == cafe.id


@pytest.mark.asyncio
async def test_ingest_resolves_category_by_leaf_name(seeded):
    """LLM sometimes emits just the leaf ("Cafe") — resolver falls back to name match."""
    async with SessionLocal() as session:
        parent = Category(name="Ăn uống", kind="expense", path="Ăn uống")
        session.add(parent)
        await session.flush()
        cafe = Category(
            name="Cafe", kind="expense", path="Ăn uống > Cafe", parent_id=parent.id
        )
        session.add(cafe)
        await session.commit()

        parsed = ParsedTx(
            amount=Decimal("30000"),
            kind="expense",
            account_hint="VCB",
            rule_name="llm-fallback",
            category="Cafe",  # leaf-only
        )
        tx = await ingest_parsed(session, parsed, message_id="m-cat-leaf")
        assert tx is not None
        assert tx.category_id == cafe.id


@pytest.mark.asyncio
async def test_ingest_unknown_category_falls_back_null(seeded):
    """If LLM invents a category that doesn't exist, we don't block — category
    stays NULL and user can triage in UI."""
    async with SessionLocal() as session:
        parsed = ParsedTx(
            amount=Decimal("10000"),
            kind="expense",
            account_hint="VCB",
            rule_name="llm-fallback",
            category="Nothing > Fictional",
        )
        tx = await ingest_parsed(session, parsed, message_id="m-cat-none")
        assert tx is not None
        assert tx.category_id is None


@pytest.mark.asyncio
async def test_resolve_category_by_name_case_insensitive(seeded):
    """Matching is case-insensitive and tolerates minor whitespace differences."""
    async with SessionLocal() as session:
        c = Category(name="Grab", kind="expense", path="Đi lại > Grab")
        session.add(c)
        await session.commit()

        # exact path, mixed case
        cid = await _resolve_category_by_name(session, "đi LẠI > grab", "expense")
        assert cid == c.id
        # leaf only
        cid = await _resolve_category_by_name(session, "GRAB", "expense")
        assert cid == c.id
        # Kind mismatch now falls back cross-kind (so an income row tagged with
        # "Chưa phân loại" — seeded only as expense — still lands somewhere).
        # Same-kind matches are preferred over cross-kind when both exist.
        cid = await _resolve_category_by_name(session, "Grab", "income")
        assert cid == c.id


@pytest.mark.asyncio
async def test_extract_email_schema_includes_category():
    """Regression guard: the schema sent to the LLM must declare the category
    field so JSON-mode models don't drop it."""
    from money_api.llm.prompts.extract_email import EXTRACT_EMAIL_SCHEMA

    assert "category" in EXTRACT_EMAIL_SCHEMA["properties"]
    assert EXTRACT_EMAIL_SCHEMA["properties"]["category"] == {
        "type": ["string", "null"]
    }


@pytest.mark.asyncio
async def test_ingest_parsed_creates_pending_tx(seeded):
    async with SessionLocal() as session:
        parsed = ParsedTx(
            amount=Decimal("450000"),
            currency="VND",
            kind="expense",
            merchant="GRAB HCM",
            account_hint="VCB",
            ts=datetime(2026, 4, 22, 12, 30),
            note="VCB giao dich",
            rule_name="VCB",
        )
        tx = await ingest_parsed(session, parsed, message_id="m1")
        assert tx is not None
        assert tx.source == "gmail:vcb"
        assert tx.status == "pending"
        assert tx.raw_ref == "m1"
        assert tx.amount == Decimal("-450000")
        await session.commit()

        # Dedup: same message_id → second call returns None
        parsed2 = ParsedTx(
            amount=Decimal("450000"),
            currency="VND",
            kind="expense",
            merchant="GRAB",
            account_hint="VCB",
            ts=datetime(2026, 4, 22, 12, 30),
            rule_name="VCB",
        )
        tx2 = await ingest_parsed(session, parsed2, message_id="m1")
        assert tx2 is None


@pytest.mark.asyncio
async def test_ingest_parsed_no_account_hint_match(seeded):
    async with SessionLocal() as session:
        parsed = ParsedTx(
            amount=Decimal("100000"),
            currency="VND",
            kind="expense",
            account_hint="NonExistentBank",
            ts=datetime(2026, 4, 22),
            rule_name="FakeRule",
        )
        tx = await ingest_parsed(session, parsed, message_id="no-match")
        assert tx is None


@pytest.mark.asyncio
async def test_ingest_parsed_income_positive(seeded):
    async with SessionLocal() as session:
        parsed = ParsedTx(
            amount=Decimal("25000000"),
            currency="VND",
            kind="income",
            merchant="Salary",
            account_hint="VCB",
            ts=datetime(2026, 4, 22),
            rule_name="VCB",
        )
        tx = await ingest_parsed(session, parsed, message_id="inc1")
        assert tx is not None
        assert tx.amount == Decimal("25000000")
