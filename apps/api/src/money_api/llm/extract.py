"""Fast path: structured extract of transactions from chat text."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Account, Merchant
from .category_match import load_user_categories, validate_llm_category
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
    paths, canonical = await load_user_categories(
        session, kinds=["expense", "income"]
    )
    mc_rows = (await session.execute(select(Merchant.name).limit(30))).all()
    tz = ZoneInfo(get_settings().tz)
    return {
        "accounts": [{"name": r.name, "type": r.type, "currency": r.currency} for r in acc_rows],
        # Plain paths — drop the `[kind]` prefix that confused the LLM into
        # echoing the prefix back. Kind is a separate JSON field; the path
        # alone is what `category` should hold.
        "categories": paths,
        "category_canonical": canonical,
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
        items = data
    elif isinstance(data, dict):
        if "transactions" in data and isinstance(data["transactions"], list):
            items = data["transactions"]
        elif "amount" in data:
            items = [data]
        else:
            items = []
    else:
        items = []

    # Strict-validate every item's `category` against the user's actual
    # category tree. LLM outputs that don't match (hallucinations,
    # paraphrases like "Coffee shop") become null so the resolver falls
    # cleanly to "Chưa phân loại" instead of fuzzy-matching to a wrong row.
    canonical = ctx.get("category_canonical") or {}
    for it in items:
        if not isinstance(it, dict):
            continue
        raw_cat = it.get("category")
        validated = validate_llm_category(raw_cat, canonical)
        if validated is None and isinstance(raw_cat, str) and raw_cat.strip():
            log.info(
                "chat extract proposed category %r not in user list — dropping",
                raw_cat,
            )
        it["category"] = validated

    return {"transactions": items}
