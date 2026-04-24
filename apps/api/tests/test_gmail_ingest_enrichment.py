"""Test source enrichment + note handling for email-ingested transactions."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_api.db import SessionLocal
from money_api.ingest.gmail_parser import ParsedTx
from money_api.ingest.gmail_poller import _source_for, ingest_parsed


def _make(**k) -> ParsedTx:
    defaults = dict(
        amount=Decimal("100000"),
        currency="VND",
        kind="expense",
        merchant=None,
        account_hint="VCB",
        is_credit_card=False,
        ts=datetime(2026, 4, 22, 12, 0, 0),
        note=None,
        rule_name="VCB",
        confidence=0.9,
        extra={"sender": "a@b.com", "message_id": "m1"},
    )
    defaults.update(k)
    return ParsedTx(**defaults)


def test_source_slugifies_rule():
    assert _source_for("HSBC-credit-card") == "gmail:hsbc-credit-card"
    assert _source_for("Timo") == "gmail:timo"
    assert _source_for("llm-fallback") == "gmail:llm-fallback"
    assert _source_for("VCB Credit Card") == "gmail:vcb-credit-card"
    assert _source_for(None) == "gmail:unknown"


@pytest.mark.asyncio
async def test_ingest_writes_specific_source_and_no_tag_rows(seeded):
    async with SessionLocal() as session:
        p = _make(
            rule_name="HSBC-credit-card",
            is_credit_card=True,
            account_hint="VCB",
            merchant="GS25 VN0037",
            amount=Decimal("37000"),
        )
        tx = await ingest_parsed(session, p, message_id="enrich-m1")
        assert tx is not None
        assert tx.source == "gmail:hsbc-credit-card"
        assert tx.note is None  # subject-derived note dropped
        await session.commit()
