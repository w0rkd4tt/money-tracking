"""Gmail polling loop: history-based incremental sync → rule parser → insert transactions."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Account, Category, SyncState, Transaction
from .gmail_llm import llm_classify_email_category, llm_extract_from_email
from .gmail_oauth import load_credentials
from .gmail_parser import ParsedTx, parse_email, raw_email_from_gmail

log = logging.getLogger(__name__)

SYNC_KEY_HISTORY = "gmail.history_id"
SYNC_KEY_LAST_RUN = "gmail.last_run_at"


@dataclass
class SyncResult:
    ok: bool = True
    processed: int = 0
    ingested: int = 0
    skipped: int = 0
    errors: int = 0
    marked_read: int = 0
    llm_fallback_used: int = 0
    history_id: str | None = None
    message: str = ""


async def _get_sync_state(session: AsyncSession, key: str) -> str | None:
    row = (await session.execute(select(SyncState).where(SyncState.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _set_sync_state(session: AsyncSession, key: str, value: str) -> None:
    row = (await session.execute(select(SyncState).where(SyncState.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(SyncState(key=key, value=value))


def _build_service(creds):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _mark_read(svc, message_id: str) -> None:
    """Remove UNREAD label so next `is:unread` query skips this message.

    Requires gmail.modify scope — raises HttpError 403 if granted only readonly.
    Caller should catch + warn, not abort the whole sync.
    """
    svc.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


def _resolve_account_by_hint(
    session: AsyncSession,
    hint: str | None,
    accounts: list[Account],
    *,
    prefer_credit: bool = False,
) -> Account | None:
    if not hint:
        return None
    h = hint.lower()

    # If prefer_credit → filter to credit accounts first
    pool = accounts
    if prefer_credit:
        credit = [a for a in accounts if a.type == "credit"]
        if credit:
            pool = credit
    else:
        # Prefer non-credit accounts for regular hits so a bank email doesn't
        # accidentally match a credit-card account with the same issuer name.
        non_credit = [a for a in accounts if a.type != "credit"]
        if non_credit:
            pool = non_credit

    for a in pool:
        if a.name.lower() == h:
            return a
    for a in pool:
        if h in a.name.lower() or a.name.lower() in h:
            return a
    # Fallback: any pool (even credit, if we preferred non-credit)
    for a in accounts:
        if a.name.lower() == h:
            return a
    for a in accounts:
        if h in a.name.lower() or a.name.lower() in h:
            return a
    return None


async def _get_or_create_transfer_category(session: AsyncSession) -> int:
    from ..services.transfers import _get_transfer_category

    return await _get_transfer_category(session)


async def _resolve_category_by_name(
    session: AsyncSession, raw: str | None, kind: str
) -> int | None:
    """Look up a category by the LLM-emitted / rule-hinted string.

    Match ladder (stops at first hit):
      1. path ilike `raw` AND kind matches
      2. leaf ilike tail(raw) AND kind matches
      3. fuzzy contains leaf AND kind matches
      4. path ilike `raw`, ANY kind (kind-relaxed) — catches "Chưa phân loại"
         which is seeded only under kind=expense but is sensible for any kind
      5. fuzzy contains leaf, ANY kind — last resort
    """
    if not raw:
        return None
    name = raw.strip()
    if not name:
        return None
    leaf = name.split(">")[-1].strip()

    # 1. Exact path + kind
    row = (
        await session.execute(
            select(Category.id).where(
                Category.path.ilike(name), Category.kind == kind
            )
        )
    ).first()
    if row:
        return row[0]
    # 2. Leaf + kind
    if leaf and leaf != name:
        row = (
            await session.execute(
                select(Category.id).where(
                    Category.name.ilike(leaf), Category.kind == kind
                )
            )
        ).first()
        if row:
            return row[0]
    # 3. Fuzzy contains + kind
    row = (
        await session.execute(
            select(Category.id)
            .where(Category.name.ilike(f"%{leaf or name}%"), Category.kind == kind)
            .limit(1)
        )
    ).first()
    if row:
        return row[0]

    # --- Kind-relaxed passes ---
    # 4. Exact path, ANY kind
    row = (
        await session.execute(
            select(Category.id).where(Category.path.ilike(name)).limit(1)
        )
    ).first()
    if row:
        return row[0]
    # 5. Fuzzy contains, ANY kind
    row = (
        await session.execute(
            select(Category.id)
            .where(Category.name.ilike(f"%{leaf or name}%"))
            .limit(1)
        )
    ).first()
    return row[0] if row else None


async def _resolve_category_for(
    session: AsyncSession, kind: str, parsed_category: str | None = None
) -> int | None:
    if kind == "transfer":
        return await _get_or_create_transfer_category(session)
    # If the parser (rule or LLM) supplied a category, try to resolve it.
    if parsed_category:
        resolved = await _resolve_category_by_name(session, parsed_category, kind)
        if resolved is not None:
            return resolved
    # Last-resort triage bucket so a row never lands totally uncategorized.
    # User can re-classify from `/transactions` (click ✎ Edit) later.
    fallback = await _resolve_category_by_name(
        session, "Chưa phân loại", kind
    )
    return fallback


async def _dedup_exists(session: AsyncSession, message_id: str) -> bool:
    """Check whether this Gmail message has an *active* (non-rejected) tx.

    Rejected tx are intentionally excluded so the user can re-parse: reject
    something that was wrong, mark the email unread on Gmail, and the next
    sync will create a fresh pending row instead of silently skipping. The
    old rejected row stays for audit; user can delete it manually if they
    want a clean history.

    Source column can be 'gmail' (legacy) or 'gmail:<rule>' (new). Match
    prefix.
    """
    q = select(Transaction.id).where(
        Transaction.source.startswith("gmail"),
        Transaction.raw_ref == message_id,
        Transaction.status != "rejected",
    )
    row = (await session.execute(q.limit(1))).first()
    return row is not None


def _source_for(rule_name: str | None) -> str:
    """Produce a specific source string like 'gmail:timo', 'gmail:hsbc-credit-card',
    'gmail:llm-fallback'. Preserves 'gmail' prefix so existing filters still work.
    """
    slug = (rule_name or "unknown").strip().lower().replace(" ", "-").replace("_", "-")
    return f"gmail:{slug}"


async def ingest_parsed(
    session: AsyncSession,
    parsed: ParsedTx,
    message_id: str,
    *,
    default_account_id: int | None = None,
) -> Transaction | None:
    if await _dedup_exists(session, message_id):
        return None
    accounts = (await session.execute(select(Account).where(Account.archived.is_(False)))).scalars().all()
    acct = _resolve_account_by_hint(
        session,
        parsed.account_hint,
        accounts,
        prefer_credit=parsed.is_credit_card,
    )
    if acct is None and default_account_id is not None:
        acct = await session.get(Account, default_account_id)
    if acct is None:
        log.warning(
            "no account match for hint=%s (credit=%s), skipping message_id=%s",
            parsed.account_hint,
            parsed.is_credit_card,
            message_id,
        )
        return None

    category_id = await _resolve_category_for(
        session, parsed.kind, parsed_category=parsed.category
    )

    # Credit-card payment dedup: if the user already linked a Timo→HSBC
    # transfer (via /transactions/{id}/link-credit-payment), the credit-leg
    # tx already exists with status=confirmed. When HSBC's confirming email
    # arrives days later, we'd otherwise insert a duplicate +amount row.
    # Detect by (account, amount, ts ±3 days) and skip — caller marks email
    # as read so we don't keep re-checking.
    if parsed.kind == "income" and acct.type == "credit":
        from datetime import timedelta as _td
        ts = parsed.ts or datetime.now()
        existing_leg = (
            await session.execute(
                select(Transaction.id)
                .where(
                    Transaction.account_id == acct.id,
                    Transaction.amount == parsed.amount,
                    Transaction.ts.between(ts - _td(days=3), ts + _td(days=3)),
                    Transaction.transfer_group_id.isnot(None),
                    Transaction.status == "confirmed",
                )
                .limit(1)
            )
        ).first()
        if existing_leg is not None:
            log.info(
                "skipping credit-leg dedup for %s — already accounted for "
                "via transfer leg tx#%s",
                message_id,
                existing_leg[0],
            )
            return None

    # Sign convention per account type:
    #   Regular accounts (cash/bank/ewallet/saving):
    #     expense → negative (balance down)
    #     income  → positive (balance up)
    #   Credit card account:
    #     expense → negative (balance more negative = debt up)
    #     income  → positive (balance up toward 0 = debt down, e.g. payment/refund)
    # So the sign logic is the same in both cases; debt is derived from negative balance.
    signed: Decimal
    if parsed.kind == "expense":
        signed = -parsed.amount
    elif parsed.kind == "income":
        signed = parsed.amount
    else:
        # Transfer: skip for MVP (requires 2 accounts to be unambiguous)
        log.info("skipping transfer-kind email %s (no to_account hint)", message_id)
        return None

    # Note: skip subject (redundant — rule_name + sender already in llm_tags,
    # merchant_text holds the actual description line from body).
    # Keep parsed.note only if it looks like a user-meaningful description
    # rather than a copy of the subject.
    note_val: str | None = None
    if parsed.note:
        n = parsed.note.strip()
        # Drop if it's the subject verbatim (we often store subject in note for LLM)
        if not n.lower().startswith("[llm]") and "thông báo" not in n.lower():
            note_val = n[:200]

    source = _source_for(parsed.rule_name)

    # If the user previously rejected a parse for this email, recycle that
    # row instead of inserting a new one. The unique (source, raw_ref) DB
    # constraint would otherwise fail. App-level dedup ignores rejected so
    # we only get here when the user genuinely wants a fresh parse.
    # Match by raw_ref + gmail-prefix (source may have flipped between runs,
    # e.g. previously gmail:llm-fallback because the rule missed, now
    # gmail:timo because we relaxed the rule subject filter). Only one
    # rejected row per email is expected.
    rejected_tx = (
        await session.execute(
            select(Transaction).where(
                Transaction.raw_ref == message_id,
                Transaction.source.startswith("gmail"),
                Transaction.status == "rejected",
            )
        )
    ).scalar_one_or_none()
    if rejected_tx is not None:
        rejected_tx.ts = parsed.ts or datetime.now()
        rejected_tx.amount = signed
        rejected_tx.currency = parsed.currency
        rejected_tx.account_id = acct.id
        rejected_tx.category_id = category_id
        rejected_tx.merchant_text = parsed.merchant
        rejected_tx.note = note_val
        rejected_tx.source = source
        rejected_tx.confidence = parsed.confidence
        rejected_tx.status = "pending"
        rejected_tx.llm_tags = {"rule": parsed.rule_name, "extra": parsed.extra}
        await session.flush()
        return rejected_tx

    tx = Transaction(
        ts=parsed.ts or datetime.now(),
        amount=signed,
        currency=parsed.currency,
        account_id=acct.id,
        category_id=category_id,
        merchant_text=parsed.merchant,
        note=note_val,
        source=source,
        raw_ref=message_id,
        confidence=parsed.confidence,
        status="pending",
        llm_tags={"rule": parsed.rule_name, "extra": parsed.extra},
    )
    session.add(tx)
    await session.flush()
    return tx


async def poll_once(
    session: AsyncSession, *, query: str | None = None
) -> SyncResult:
    """Run one sync iteration. Processes UNREAD emails only — dedup by message_id
    ensures an email already ingested is skipped if user marks it unread again.

    We deliberately skip Gmail `history.list` (complex, historyId expires after 7d)
    and just query unread messages in the last 7 days. Simpler, more reliable, and
    matches the user's intent: "only read unread emails".
    """
    creds = await load_credentials(session)
    if creds is None:
        return SyncResult(ok=False, message="Gmail not connected")
    try:
        svc = await asyncio.to_thread(_build_service, creds)
    except Exception as e:
        return SyncResult(ok=False, message=f"failed to build gmail service: {e}")

    result = SyncResult()
    msg_ids: list[str] = []
    new_hist: str | None = None
    try:
        # List unread messages from the last 7 days. Gmail `q` syntax:
        # https://support.google.com/mail/answer/7190
        # `is:unread` matches messages without the UNREAD label absent → wait, we want WITH UNREAD label.
        # Correct: `is:unread` = has UNREAD label = not yet read.
        # Default: only unread inbox emails in last 7d. Overridable to re-read
        # all emails after a DB wipe or to backfill a longer window.
        q = query or "is:unread in:inbox newer_than:7d"
        page_token: str | None = None
        while True:
            params: dict = {"userId": "me", "q": q, "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token
            resp = await asyncio.to_thread(
                lambda p=params: svc.users().messages().list(**p).execute()
            )
            for m in resp.get("messages", []):
                msg_ids.append(m["id"])
            page_token = resp.get("nextPageToken")
            if not page_token or len(msg_ids) >= 500:  # safety cap
                break

        # Save current historyId for reference (not used for sync anymore)
        try:
            prof = await asyncio.to_thread(
                lambda: svc.users().getProfile(userId="me").execute()
            )
            new_hist = prof.get("historyId")
        except Exception:
            new_hist = None

        from ..config import get_settings as _get_settings

        _cfg = _get_settings()
        should_mark = _cfg.gmail_mark_read_after_ingest
        llm_fallback_enabled = _cfg.gmail_llm_fallback
        llm_max_body = _cfg.gmail_llm_max_body_chars

        for mid in msg_ids:
            try:
                msg = await asyncio.to_thread(
                    lambda m=mid: svc.users()
                    .messages()
                    .get(userId="me", id=m, format="full")
                    .execute()
                )
                result.processed += 1
                raw = raw_email_from_gmail(msg)

                # Early dedup — if we already ingested this message in a
                # previous run, don't re-parse (skip LLM call entirely) and just
                # mark it read so the next sync stops pulling it back.
                if await _dedup_exists(session, mid):
                    if should_mark:
                        try:
                            await asyncio.to_thread(_mark_read, svc, mid)
                            result.marked_read += 1
                        except HttpError as e:
                            log.warning(
                                "mark-read failed for %s: %s (need gmail.modify scope?)",
                                mid,
                                e,
                            )
                    result.skipped += 1
                    continue

                parsed = parse_email(raw)
                if parsed is None and llm_fallback_enabled:
                    # Rule miss → ask LLM to read the body
                    if len(raw.body_text or "") <= llm_max_body:
                        log.info(
                            "rule miss for %s, trying LLM fallback (sender=%s)",
                            mid,
                            raw.from_addr,
                        )
                        parsed = await llm_extract_from_email(session, raw)
                        if parsed is not None:
                            result.llm_fallback_used += 1
                if parsed is None:
                    # Still no match → leave unread so user can review / add rule
                    result.skipped += 1
                    continue

                # Rule extracted but didn't pick a category (most bank emails
                # land here — rule knows amount/account/ts but not whether
                # the merchant is "Ăn uống" or "Đi lại"). Run a focused LLM
                # classify on the body so the resolver has something better
                # than "Chưa phân loại" to map.
                if (
                    parsed.rule_name != "llm-fallback"
                    and (parsed.category is None or parsed.category == "Chưa phân loại")
                    and llm_fallback_enabled
                    and len(raw.body_text or "") <= llm_max_body
                ):
                    classified = await llm_classify_email_category(
                        session,
                        raw,
                        merchant=parsed.merchant,
                        amount=int(parsed.amount),
                        kind=parsed.kind,
                    )
                    if classified:
                        log.info(
                            "LLM classify category for %s: %s (rule=%s)",
                            mid,
                            classified,
                            parsed.rule_name,
                        )
                        parsed.category = classified
                tx = await ingest_parsed(session, parsed, mid)
                mark = False
                if tx is not None:
                    result.ingested += 1
                    mark = True  # freshly ingested
                else:
                    # ingest_parsed returned None: either dedup (already exists
                    # with this raw_ref) or account-hint did not resolve.
                    # Mark read only if an *active* entry exists (dedup) —
                    # rejected tx don't count, so a user re-marking an email
                    # unread to retry a previously-failed parse won't be
                    # immediately re-flagged read.
                    existing = (
                        await session.execute(
                            select(Transaction.id)
                            .where(
                                Transaction.source.startswith("gmail"),
                                Transaction.raw_ref == mid,
                                Transaction.status != "rejected",
                            )
                            .limit(1)
                        )
                    ).first()
                    if existing:
                        mark = True
                    else:
                        # Account hint did not resolve — keep unread so user
                        # can create the missing account and resync.
                        pass
                    result.skipped += 1

                if mark and should_mark:
                    try:
                        await asyncio.to_thread(_mark_read, svc, mid)
                        result.marked_read += 1
                    except HttpError as e:
                        # 403 typically means scope insufficient (readonly)
                        log.warning(
                            "mark-read failed for %s (%s) — reconnect Gmail "
                            "with gmail.modify scope",
                            mid,
                            e,
                        )
            except Exception as e:
                result.errors += 1
                log.exception("failed to process message %s: %s", mid, e)

        await _set_sync_state(session, SYNC_KEY_HISTORY, str(new_hist))
        await _set_sync_state(session, SYNC_KEY_LAST_RUN, datetime.utcnow().isoformat())
        await session.commit()
        result.history_id = str(new_hist)
        result.message = "ok"
    except HttpError as e:
        result.ok = False
        result.message = f"Gmail API error: {e}"
        log.error("poll error: %s", e)
    except Exception as e:
        result.ok = False
        result.message = f"unexpected error: {e}"
        log.exception("poll error")

    return result


async def run_forever(interval_sec: int | None = None):
    """Long-running background task — calls poll_once at fixed interval."""
    from ..db import SessionLocal

    interval = interval_sec or get_settings().gmail_poll_interval_sec
    log.info("gmail poller started, interval=%ss", interval)
    while True:
        try:
            async with SessionLocal() as session:
                r = await poll_once(session)
                if not r.ok:
                    log.info("poll skipped: %s", r.message)
                else:
                    log.info(
                        "poll ok: processed=%d ingested=%d skipped=%d errors=%d hist=%s",
                        r.processed,
                        r.ingested,
                        r.skipped,
                        r.errors,
                        r.history_id,
                    )
        except Exception as e:
            log.exception("poll loop iter error: %s", e)
        await asyncio.sleep(interval)


# Silence unused-import warnings for tools analysing the file.
_ = Category
_ = re
_ = timedelta
