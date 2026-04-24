"""LLM fallback tests. Mock the provider to avoid hitting Ollama."""

from datetime import datetime
from unittest.mock import patch

import pytest

from money_api.db import SessionLocal
from money_api.ingest.gmail_llm import _parse_ts_with_time, llm_extract_from_email
from money_api.ingest.gmail_parser import RawEmail


def test_parse_ts_detects_missing_time_component():
    """Date-only strings parse to midnight but report has_time=False so callers
    can prefer the email received_at header instead."""
    dt, has_time = _parse_ts_with_time("2026-04-23")
    assert dt == datetime(2026, 4, 23, 0, 0)
    assert has_time is False

    dt, has_time = _parse_ts_with_time("2026-04-23T14:23:45")
    assert dt == datetime(2026, 4, 23, 14, 23, 45)
    assert has_time is True

    dt, has_time = _parse_ts_with_time("2026-04-23 09:00:00")
    assert has_time is True

    dt, has_time = _parse_ts_with_time("not-a-date")
    assert dt is None and has_time is False

    dt, has_time = _parse_ts_with_time(None)
    assert dt is None and has_time is False


@pytest.mark.asyncio
async def test_llm_extract_date_only_prefers_received_at(seeded):
    """If LLM emits date-only ts, ingest should use raw.received_at (which has
    real wall-clock seconds) instead of midnight."""
    received_at = datetime(2026, 4, 23, 14, 23, 45)
    raw = RawEmail(
        message_id="dateonly-1",
        from_addr="bank@example.com",
        subject="Giao dịch",
        body_text="Thẻ của bạn đã thanh toán 258,000 VND.",
        received_at=received_at,
    )
    fake_data = {
        "is_transaction": True,
        "amount": 258000,
        "currency": "VND",
        "kind": "expense",
        "is_credit_card": True,
        "account_hint": "HSBC",
        "merchant": "CAFE",
        "ts": "2026-04-23",  # <-- date-only, the bug condition
        "confidence": 0.9,
    }

    class _FakeProvider:
        async def chat(self, *_, **__):
            return fake_data

    with patch(
        "money_api.ingest.gmail_llm.resolve_provider",
        return_value=_FakeProvider(),
    ):
        async with SessionLocal() as session:
            parsed = await llm_extract_from_email(session, raw)

    assert parsed is not None
    assert parsed.ts == received_at, (
        f"expected fallback to received_at, got {parsed.ts}"
    )


@pytest.mark.asyncio
async def test_llm_extract_midnight_placeholder_prefers_received_at(seeded):
    """LLMs emit '2026-04-23T00:00:00' when the email body only has a date —
    a full-ISO format with a midnight time-of-day placeholder. Treat this as
    'LLM doesn't know the time' and prefer received_at."""
    received_at = datetime(2026, 4, 23, 22, 14, 5)
    raw = RawEmail(
        message_id="midnight-1",
        from_addr="hsbc@example.com",
        subject="Giao dich",
        body_text="thanh toan 258,000 VND tai CAFE vao ngay 23/04/2026.",
        received_at=received_at,
    )
    fake_data = {
        "is_transaction": True,
        "amount": 258000,
        "currency": "VND",
        "kind": "expense",
        "account_hint": "HSBC",
        "ts": "2026-04-23T00:00:00",  # <-- midnight placeholder, has ":" so format looks full
        "confidence": 0.9,
    }

    class _FakeProvider:
        async def chat(self, *_, **__):
            return fake_data

    with patch(
        "money_api.ingest.gmail_llm.resolve_provider",
        return_value=_FakeProvider(),
    ):
        async with SessionLocal() as session:
            parsed = await llm_extract_from_email(session, raw)

    assert parsed is not None
    assert parsed.ts == received_at, (
        f"midnight placeholder must defer to received_at, got {parsed.ts}"
    )


@pytest.mark.asyncio
async def test_llm_extract_full_datetime_wins_over_received_at(seeded):
    """When LLM has the exact time from body, use it (header is a few seconds
    after the actual transaction happened)."""
    raw = RawEmail(
        message_id="fullts-1",
        from_addr="bank@example.com",
        subject="Giao dịch",
        body_text="Thời gian: 14:23:45 23/04/2026",
        received_at=datetime(2026, 4, 23, 14, 23, 59),
    )
    fake_data = {
        "is_transaction": True,
        "amount": 50000,
        "currency": "VND",
        "kind": "expense",
        "account_hint": "HSBC",
        "ts": "2026-04-23T14:23:45",
        "confidence": 0.9,
    }

    class _FakeProvider:
        async def chat(self, *_, **__):
            return fake_data

    with patch(
        "money_api.ingest.gmail_llm.resolve_provider",
        return_value=_FakeProvider(),
    ):
        async with SessionLocal() as session:
            parsed = await llm_extract_from_email(session, raw)

    assert parsed is not None
    assert parsed.ts == datetime(2026, 4, 23, 14, 23, 45)


def _email(
    sender: str = "notify@somebank.co",
    subject: str = "Giao dịch thẻ",
    body: str = "Card X9999 charged VND 150000 at Highland Coffee on 22/04/2026",
) -> RawEmail:
    return RawEmail(
        message_id="llm-m1",
        from_addr=sender,
        subject=subject,
        body_text=body,
        received_at=datetime(2026, 4, 22, 12, 0, 0),
    )


@pytest.mark.asyncio
async def test_llm_fallback_extracts_expense(seeded):
    fake_json = {
        "is_transaction": True,
        "amount": 150000,
        "currency": "VND",
        "kind": "expense",
        "is_credit_card": False,
        "account_hint": "VCB",
        "merchant": "Highland Coffee",
        "ts": "2026-04-22T12:00:00",
        "confidence": 0.88,
    }
    async with SessionLocal() as session:
        with patch(
            "money_api.llm.provider.OllamaProvider.chat",
            return_value=fake_json,
        ):
            parsed = await llm_extract_from_email(session, _email())
        assert parsed is not None
        assert parsed.kind == "expense"
        assert int(parsed.amount) == 150000
        assert parsed.merchant == "Highland Coffee"
        assert parsed.account_hint == "VCB"
        assert parsed.rule_name == "llm-fallback"


@pytest.mark.asyncio
async def test_llm_fallback_rejects_non_transaction(seeded):
    fake_json = {
        "is_transaction": False,
        "reason": "OTP email",
    }
    async with SessionLocal() as session:
        with patch(
            "money_api.llm.provider.OllamaProvider.chat",
            return_value=fake_json,
        ):
            parsed = await llm_extract_from_email(
                session, _email(subject="OTP", body="Your OTP is 123456")
            )
        assert parsed is None


@pytest.mark.asyncio
async def test_llm_fallback_gracefully_on_unavailable(seeded):
    from money_api.llm.provider import LLMUnavailable

    async def raise_err(*a, **k):
        raise LLMUnavailable("Ollama down")

    async with SessionLocal() as session:
        with patch("money_api.llm.provider.OllamaProvider.chat", side_effect=raise_err):
            parsed = await llm_extract_from_email(session, _email())
        assert parsed is None


@pytest.mark.asyncio
async def test_llm_fallback_handles_list_shape(seeded):
    """Some models return [{...}] instead of {...}. Both should work."""
    fake_list = [
        {
            "is_transaction": True,
            "amount": 75000,
            "currency": "VND",
            "kind": "income",
            "is_credit_card": False,
            "account_hint": "Momo",
            "merchant": "Hoàn tiền",
            "ts": "2026-04-22T10:00:00",
            "confidence": 0.9,
        }
    ]
    async with SessionLocal() as session:
        with patch(
            "money_api.llm.provider.OllamaProvider.chat",
            return_value=fake_list,
        ):
            parsed = await llm_extract_from_email(session, _email())
        assert parsed is not None
        assert parsed.kind == "income"
        assert int(parsed.amount) == 75000
