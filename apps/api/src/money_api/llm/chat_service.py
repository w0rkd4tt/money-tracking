"""End-to-end chat → extracted transactions → saved pending transactions."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Account, Category, ChatMessage, ChatSession, Transaction
from ..schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ExtractedTransaction,
)
from .extract import extract_transactions
from .provider import LLMProviderNotFound, resolve_provider

log = logging.getLogger(__name__)


_VI_NOW_PATTERNS = re.compile(
    r"(sáng|trưa|chiều|tối|đêm|hôm qua|hôm nay|tuần trước|tháng trước)",
    re.IGNORECASE,
)


async def _get_or_create_session(
    session: AsyncSession, channel: str, external_id: str
) -> ChatSession:
    q = select(ChatSession).where(
        ChatSession.channel == channel, ChatSession.external_id == external_id
    )
    existing = (await session.execute(q)).scalar_one_or_none()
    if existing:
        return existing
    cs = ChatSession(channel=channel, external_id=external_id)
    session.add(cs)
    await session.flush()
    return cs


async def _resolve_account(session: AsyncSession, name: str | None) -> int | None:
    if not name:
        return None
    q = select(Account.id).where(Account.name.ilike(name))
    row = (await session.execute(q)).first()
    if row:
        return row[0]
    # fallback: case-insensitive contains
    q2 = select(Account.id).where(Account.name.ilike(f"%{name}%"))
    row2 = (await session.execute(q2)).first()
    return row2[0] if row2 else None


async def _resolve_category(session: AsyncSession, path: str | None) -> int | None:
    if not path:
        return None
    q = select(Category.id).where(Category.path.ilike(path))
    row = (await session.execute(q)).first()
    if row:
        return row[0]
    # fallback partial match
    last = path.split(">")[-1].strip()
    q2 = select(Category.id).where(Category.name.ilike(f"%{last}%"))
    row2 = (await session.execute(q2)).first()
    return row2[0] if row2 else None


def _parse_ts(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.now()
    tz = ZoneInfo(get_settings().tz)
    if dt.tzinfo is None:
        return dt
    # Normalize to local tz and drop tzinfo — DB column is TIMESTAMP WITHOUT TZ.
    return dt.astimezone(tz).replace(tzinfo=None)


async def process_chat(session: AsyncSession, req: ChatMessageRequest) -> ChatMessageResponse:
    cs = await _get_or_create_session(session, req.channel, req.external_id)
    session.add(ChatMessage(session_id=cs.id, role="user", content=req.text))

    # Resolve the provider up-front so every response branch reports truthfully
    # which one handled the turn. If the caller supplied an unknown name, fall
    # back to the default (rather than 500-ing the whole request).
    try:
        active_provider = (
            await resolve_provider(session, preferred=req.provider)
        ).name
    except LLMProviderNotFound:
        active_provider = (await resolve_provider(session, preferred=None)).name

    raw = await extract_transactions(session, req.text, provider_name=req.provider)
    txs_raw: list[dict[str, Any]] = raw.get("transactions") or []
    err = raw.get("error")

    if not txs_raw:
        reply = (
            "Không phát hiện giao dịch nào trong câu. "
            "Bạn thử mô tả rõ hơn (số tiền + account)."
        )
        if err:
            reply = f"LLM tạm không khả dụng ({err}). Hãy thử lại hoặc dùng form nhập tay."
        session.add(ChatMessage(session_id=cs.id, role="assistant", content=reply))
        return ChatMessageResponse(
            intent="unknown", reply_text=reply, provider=active_provider
        )

    extracted: list[ExtractedTransaction] = []
    intent = "create_transaction"
    for item in txs_raw:
        # Field aliases some models emit.
        if "ts" not in item and "date" in item:
            item["ts"] = item.pop("date")
        if "ts" not in item and "datetime" in item:
            item["ts"] = item.pop("datetime")
        kind = item.get("kind") or "expense"
        if kind == "transfer":
            intent = "create_transfer"
        amount = int(item.get("amount") or 0)
        account_name = item.get("account") or ""
        account_id = await _resolve_account(session, account_name)
        if account_id is None:
            extracted.append(
                ExtractedTransaction(
                    amount=amount,
                    currency=item.get("currency") or "VND",
                    kind=kind,
                    account=account_name,
                    to_account=item.get("to_account"),
                    category=item.get("category"),
                    merchant=item.get("merchant"),
                    ts=_parse_ts(item.get("ts") or ""),
                    note=item.get("note"),
                    confidence=float(item.get("confidence") or 0.0),
                    ambiguous_fields=["account"],
                )
            )
            continue

        if kind == "transfer":
            to_account_name = item.get("to_account") or ""
            to_account_id = await _resolve_account(session, to_account_name)
            if to_account_id is None or to_account_id == account_id:
                # Can't persist without both distinct accounts — surface for user to fix.
                extracted.append(
                    ExtractedTransaction(
                        amount=amount,
                        currency=item.get("currency") or "VND",
                        kind=kind,
                        account=account_name,
                        to_account=to_account_name or None,
                        category="Transfer",
                        merchant=item.get("merchant"),
                        ts=_parse_ts(item.get("ts") or ""),
                        note=item.get("note"),
                        confidence=float(item.get("confidence") or 0.0),
                        ambiguous_fields=["to_account"],
                    )
                )
                continue

            from ..schemas.transfer import TransferCreate
            from ..services.transfers import TransferError, create_transfer

            try:
                tr = await create_transfer(
                    session,
                    TransferCreate(
                        ts=_parse_ts(item.get("ts") or ""),
                        from_account_id=account_id,
                        to_account_id=to_account_id,
                        amount=Decimal(amount),
                        fee=Decimal(0),
                        currency=item.get("currency") or "VND",
                        note=item.get("note"),
                    ),
                    source=f"chat_{req.channel}",
                )
            except TransferError as e:
                log.warning("transfer create failed: %s", e)
                extracted.append(
                    ExtractedTransaction(
                        amount=amount,
                        currency=item.get("currency") or "VND",
                        kind=kind,
                        account=account_name,
                        to_account=to_account_name,
                        category="Transfer",
                        ts=_parse_ts(item.get("ts") or ""),
                        note=str(e),
                        confidence=float(item.get("confidence") or 0.0),
                        ambiguous_fields=["to_account"],
                    )
                )
                continue

            extracted.append(
                ExtractedTransaction(
                    id=tr.id,
                    status="confirmed",
                    amount=amount,
                    currency=tr.currency,
                    kind=kind,
                    account=account_name,
                    to_account=to_account_name,
                    category="Transfer",
                    merchant=item.get("merchant"),
                    ts=tr.ts,
                    note=tr.note,
                    confidence=float(item.get("confidence") or 0.0),
                )
            )
            continue

        category_id = await _resolve_category(session, item.get("category"))
        signed = -amount if kind == "expense" else amount
        tx = Transaction(
            ts=_parse_ts(item.get("ts") or ""),
            amount=Decimal(signed),
            currency=item.get("currency") or "VND",
            account_id=account_id,
            category_id=category_id,
            merchant_text=item.get("merchant"),
            note=item.get("note"),
            source=f"chat_{req.channel}",
            confidence=float(item.get("confidence") or 0.0),
            status="pending",
            llm_tags={"extract_version": "v1"},
        )
        session.add(tx)
        await session.flush()
        extracted.append(
            ExtractedTransaction(
                id=tx.id,
                status=tx.status,
                amount=amount,
                currency=tx.currency,
                kind=kind,
                account=account_name,
                to_account=item.get("to_account"),
                category=item.get("category"),
                merchant=item.get("merchant"),
                ts=tx.ts,
                note=tx.note,
                confidence=tx.confidence,
            )
        )

    reply = f"Đã trích xuất {len(extracted)} giao dịch, xác nhận nhé."
    session.add(ChatMessage(session_id=cs.id, role="assistant", content=reply))
    return ChatMessageResponse(
        intent=intent,  # type: ignore[arg-type]
        transactions=extracted,
        reply_text=reply,
        provider=active_provider,
    )


_ = _VI_NOW_PATTERNS  # reserved for future heuristics
