"""LLM fallback: extract transaction from email when rule engine misses.

Flow:
  1. Build context (user accounts, categories) from DB
  2. Redact email body (cards, OTP, balance lines)
  3. Call m1ultra with EXTRACT_EMAIL_SCHEMA
  4. Normalize LLM output → ParsedTx
  5. Caller hands ParsedTx to ingest_parsed
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..llm.prompts.extract_email import (
    EXTRACT_EMAIL_SCHEMA,
    EXTRACT_EMAIL_SYSTEM_V1,
    build_user_prompt,
)
from ..llm.provider import (
    LLMInvalidOutput,
    LLMProviderNotFound,
    LLMUnavailable,
    resolve_provider,
)
from ..llm.redact import redact
from ..models import Account, Category
from .gmail_parser import ParsedTx, RawEmail

log = logging.getLogger(__name__)


async def _build_context(session: AsyncSession) -> dict[str, Any]:
    accs = (
        await session.execute(
            select(Account.name, Account.type, Account.currency).where(Account.archived.is_(False))
        )
    ).all()
    cats = (
        await session.execute(
            select(Category.path).where(Category.kind.in_(["expense", "income"]))
        )
    ).all()
    tz = ZoneInfo(get_settings().tz)
    return {
        "accounts": [{"name": a.name, "type": a.type, "currency": a.currency} for a in accs],
        "categories": [c.path for c in cats if c.path],
        "now_iso": datetime.now(tz).isoformat(),
    }


def _parse_ts_with_time(value: str | None) -> tuple[datetime | None, bool]:
    """Parse an ISO timestamp from the LLM and also report whether the string
    actually carried a time component.

    The LLM sometimes emits just ``"2026-04-23"`` (date-only). ``fromisoformat``
    happily parses that into ``datetime(2026, 4, 23, 0, 0)`` — which is indistinguishable
    from an email that genuinely happened at midnight. Returning a `has_time` flag
    lets the caller prefer the email's own ``received_at`` header (which always
    carries a real clock time) when the LLM didn't contribute one.
    """
    if not value:
        return None, False
    has_time = "T" in value or ":" in value or " " in value
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, False
    if dt.tzinfo is not None:
        tz = ZoneInfo(get_settings().tz)
        dt = dt.astimezone(tz).replace(tzinfo=None)
    return dt, has_time


def _parse_ts(value: str | None) -> datetime | None:
    """Back-compat shim — returns just the datetime (no time-flag)."""
    dt, _ = _parse_ts_with_time(value)
    return dt


async def llm_extract_from_email(
    session: AsyncSession, raw: RawEmail
) -> ParsedTx | None:
    """Send email to m1ultra and return a ParsedTx on success, None otherwise.

    Graceful on all failure modes (LLM down, JSON invalid, says not a tx).
    Caller should not rely on this for known bank formats — use rule engine
    first for speed + determinism.
    """
    ctx = await _build_context(session)

    body_redacted = redact(raw.body_text or "")
    prompt = build_user_prompt(
        accounts=ctx["accounts"],
        sender=raw.from_addr,
        subject=raw.subject,
        body_redacted=body_redacted,
        now_iso=ctx["now_iso"],
        category_hints=ctx["categories"],
    )
    messages = [
        {"role": "system", "content": EXTRACT_EMAIL_SYSTEM_V1},
        {"role": "user", "content": prompt},
    ]

    try:
        provider = await resolve_provider(session)
        data = await provider.chat(
            messages,
            schema=EXTRACT_EMAIL_SCHEMA,
            temperature=0.1,
            num_predict=800,
            think=False,
        )
    except (LLMUnavailable, LLMInvalidOutput, LLMProviderNotFound) as e:
        log.warning("LLM email extract failed for %s: %s", raw.message_id, e)
        return None

    # Normalize various shapes: {is_transaction:...}, [{...}], {"transactions":[...]}
    if isinstance(data, list) and data:
        data = data[0]
    elif isinstance(data, dict) and "transactions" in data:
        items = data.get("transactions") or []
        if not items:
            return None
        data = items[0]

    if not isinstance(data, dict):
        return None

    is_tx = bool(data.get("is_transaction"))
    if not is_tx:
        log.info(
            "LLM classified %s as non-transaction (reason=%s)",
            raw.message_id,
            data.get("reason"),
        )
        return None

    try:
        amount = int(data.get("amount") or 0)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None

    kind = data.get("kind") or "expense"
    if kind not in {"expense", "income", "transfer"}:
        kind = "expense"

    # Resolve transaction timestamp with a priority chain that respects which
    # source has reliable wall-clock precision:
    #   1. LLM returned a full datetime (has time component) → most accurate,
    #      matches the transaction's actual moment as stated in the email body
    #   2. Email header `received_at` → always has precise HH:MM:SS, usually
    #      seconds after the transaction actually occurred
    #   3. LLM returned date-only → use it but we know time is midnight filler
    #   4. datetime.now() as last resort
    llm_ts, has_time = _parse_ts_with_time(data.get("ts"))
    # Even when the format contains ":", LLMs frequently emit "00:00:00" as a
    # placeholder when the email body only has a date ("ngày 23/04/2026"). Treat
    # an exact midnight as "no real time" and fall through to received_at.
    has_real_time = (
        has_time
        and llm_ts is not None
        and (llm_ts.hour, llm_ts.minute, llm_ts.second) != (0, 0, 0)
    )
    if has_real_time:
        ts = llm_ts
    elif raw.received_at is not None:
        ts = raw.received_at
    elif llm_ts is not None:
        ts = llm_ts
    else:
        ts = datetime.now()

    return ParsedTx(
        amount=Decimal(amount),
        currency=data.get("currency") or "VND",
        kind=kind,
        merchant=(data.get("merchant") or None),
        account_hint=(data.get("account_hint") or None),
        is_credit_card=bool(data.get("is_credit_card")),
        note=f"[LLM] {raw.subject}"[:200],
        ts=ts,
        rule_name="llm-fallback",
        confidence=float(data.get("confidence") or 0.7),
        category=(data.get("category") or None),
        extra={
            "sender": raw.from_addr,
            "message_id": raw.message_id,
            "llm_reason": data.get("reason"),
        },
    )
