"""Fast path: structured extract of transactions from chat text."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Account, Category, Merchant
from .prompts.extract_chat import (
    EXTRACT_CHAT_SCHEMA,
    EXTRACT_CHAT_SYSTEM_V1,
    build_user_prompt,
)
from .provider import (
    LLMInvalidOutput,
    LLMProviderNotFound,
    LLMUnavailable,
    resolve_provider,
)

log = logging.getLogger(__name__)


async def build_context(session: AsyncSession) -> dict[str, Any]:
    acc_rows = (
        await session.execute(
            select(Account.name, Account.type, Account.currency).where(Account.archived.is_(False))
        )
    ).all()
    cat_rows = (
        await session.execute(
            select(Category.path, Category.kind).where(Category.kind.in_(["expense", "income"]))
        )
    ).all()
    mc_rows = (await session.execute(select(Merchant.name).limit(30))).all()
    tz = ZoneInfo(get_settings().tz)
    return {
        "accounts": [{"name": r.name, "type": r.type, "currency": r.currency} for r in acc_rows],
        "categories": [f"[{r.kind}] {r.path}" for r in cat_rows if r.path],
        "merchants": [r.name for r in mc_rows],
        "now_iso": datetime.now(tz).isoformat(),
    }


async def extract_transactions(
    session: AsyncSession, text: str, provider_name: str | None = None
) -> dict[str, Any]:
    ctx = await build_context(session)
    prompt = build_user_prompt(
        text=text,
        accounts=ctx["accounts"],
        categories=ctx["categories"],
        merchants=ctx["merchants"],
        now_iso=ctx["now_iso"],
    )
    messages = [
        {"role": "system", "content": EXTRACT_CHAT_SYSTEM_V1},
        {"role": "user", "content": prompt},
    ]
    try:
        provider = await resolve_provider(session, preferred=provider_name)
        data = await provider.chat(
            messages,
            schema=EXTRACT_CHAT_SCHEMA,
            temperature=0.1,
            num_predict=1024,
            think=False,
        )
    except (LLMUnavailable, LLMInvalidOutput, LLMProviderNotFound) as e:
        log.warning("extract_transactions failed: %s", e)
        return {"transactions": [], "error": str(e)}
    # Normalize response shapes:
    # - {"transactions": [...]}
    # - [{...}, ...]
    # - {"amount": ...} (single object)
    if isinstance(data, list):
        return {"transactions": data}
    if isinstance(data, dict):
        if "transactions" in data:
            return data
        if "amount" in data:
            return {"transactions": [data]}
    return {"transactions": []}
