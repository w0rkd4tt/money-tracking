"""Gmail sync + status endpoints."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal, get_session
from ..ingest.gmail_oauth import get_connected_email
from ..ingest.gmail_poller import (
    SYNC_KEY_HISTORY,
    SYNC_KEY_LAST_RUN,
    poll_once,
)
from ..models import OauthCredential, SyncState
from ..schemas.gmail import GmailStatus, GmailSyncResult, IngestedEmailItem, IngestStats

log = logging.getLogger(__name__)
router = APIRouter(prefix="/gmail", tags=["gmail"])

# Guard against concurrent syncs — Gmail API quotas + LLM throughput are both
# constrained. Running two polls in parallel doubles the work with no benefit.
_sync_lock = asyncio.Lock()
# Last completed run (in-memory). Persisted last-run is in sync_state table;
# this is for returning rich stats to the UI right after a background kick.
_last_result: dict | None = None
_running: bool = False


async def _sync_val(session: AsyncSession, key: str) -> str | None:
    row = (await session.execute(select(SyncState).where(SyncState.key == key))).scalar_one_or_none()
    return row.value if row else None


@router.get("/status", response_model=GmailStatus)
async def status(session: AsyncSession = Depends(get_session)):
    email = await get_connected_email(session)
    cred = (
        await session.execute(
            select(OauthCredential).where(OauthCredential.provider == "google").limit(1)
        )
    ).scalar_one_or_none()
    last_run_s = await _sync_val(session, SYNC_KEY_LAST_RUN)
    history = await _sync_val(session, SYNC_KEY_HISTORY)
    last_run_dt: datetime | None = None
    if last_run_s:
        try:
            last_run_dt = datetime.fromisoformat(last_run_s)
        except ValueError:
            last_run_dt = None
    scopes_str = cred.scopes if cred else None
    can_mark_read = bool(
        scopes_str and "gmail.modify" in scopes_str
    )
    return GmailStatus(
        connected=email is not None,
        account_email=email,
        scopes=scopes_str,
        expires_at=cred.expires_at if cred else None,
        last_sync_at=last_run_dt,
        last_history_id=history,
        can_mark_read=can_mark_read,
    )


@router.get("/inbox")
async def inbox_preview(
    query: str = "is:unread in:inbox newer_than:7d",
    max_results: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """Debug: list unread emails with sender/subject + whether any built-in rule
    matches by sender. Use to figure out why parse_email skipped an email."""
    import asyncio
    import re

    from ..ingest.gmail_oauth import load_credentials
    from ..ingest.gmail_parser import BUILTIN_RULES

    creds = await load_credentials(session)
    if creds is None:
        return {"connected": False, "items": []}

    from googleapiclient.discovery import build

    svc = await asyncio.to_thread(
        lambda: build("gmail", "v1", credentials=creds, cache_discovery=False)
    )
    resp = await asyncio.to_thread(
        lambda: svc.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    ids = [m["id"] for m in resp.get("messages", [])]

    def _matches(pattern: str, value: str) -> bool:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return re.search(regex, value, re.IGNORECASE) is not None

    items = []
    for mid in ids:
        try:
            msg = await asyncio.to_thread(
                lambda m=mid: svc.users()
                .messages()
                .get(
                    userId="me",
                    id=m,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            sender = headers.get("from", "")
            subject = headers.get("subject", "")
            matched_rule = None
            for r in sorted(BUILTIN_RULES, key=lambda x: -x.priority):
                if any(_matches(g, sender) for g in r.sender_globs):
                    # Sender OK; check subject filter
                    if not r.subject_any or any(
                        k.lower() in subject.lower() for k in r.subject_any
                    ):
                        matched_rule = r.name
                        break
                    elif matched_rule is None:
                        matched_rule = f"{r.name}?subject"
            items.append(
                {
                    "id": mid,
                    "from": sender,
                    "subject": subject,
                    "date": headers.get("date"),
                    "matched_rule": matched_rule,
                }
            )
        except Exception as e:
            items.append({"id": mid, "error": str(e)})
    return {"connected": True, "count": len(items), "items": items}


def _item_from_tx(
    tx, account_name: str | None, category_name: str | None
) -> IngestedEmailItem:
    tags = tx.llm_tags or {}
    extra = tags.get("extra") or {}
    rule = tags.get("rule") or None
    return IngestedEmailItem(
        transaction_id=tx.id,
        ts=tx.ts,
        amount=str(tx.amount),
        currency=tx.currency,
        status=tx.status,
        confidence=tx.confidence or 0.0,
        account_id=tx.account_id,
        account_name=account_name,
        category_id=tx.category_id,
        category_name=category_name,
        merchant=tx.merchant_text,
        note=tx.note,
        rule_name=rule,
        sender=extra.get("sender") if isinstance(extra, dict) else None,
        subject=tx.note if tx.note and tx.note.startswith("[") else None,
        message_id=tx.raw_ref,
        is_llm_fallback=(rule == "llm-fallback"),
    )


@router.get("/ingested", response_model=list[IngestedEmailItem])
async def ingested_emails(
    limit: int = 100,
    status: str | None = None,
    rule: str | None = None,
    only_llm: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """List recent email-ingested transactions with LLM metadata."""
    from sqlalchemy.orm import aliased

    from ..models import Account, Category, Transaction

    A = aliased(Account)
    C = aliased(Category)
    stmt = (
        # Use Category.path (e.g. "Ăn uống > Cafe") so the UI shows the full
        # hierarchy instead of just the leaf name — matches the transactions
        # table on /transactions.
        select(Transaction, A.name, C.path)
        .outerjoin(A, A.id == Transaction.account_id)
        .outerjoin(C, C.id == Transaction.category_id)
        # Match both "gmail" (legacy) and "gmail:<rule>" (new)
        .where(Transaction.source.startswith("gmail"))
        .order_by(Transaction.id.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Transaction.status == status)
    rows = (await session.execute(stmt)).all()
    items: list[IngestedEmailItem] = []
    for tx, acc_name, cat_name in rows:
        item = _item_from_tx(tx, acc_name, cat_name)
        if rule and item.rule_name != rule:
            continue
        if only_llm and not item.is_llm_fallback:
            continue
        items.append(item)
    return items


@router.get("/ingest-stats", response_model=IngestStats)
async def ingest_stats(session: AsyncSession = Depends(get_session)):
    from ..models import Transaction

    rows = (
        await session.execute(
            select(Transaction).where(Transaction.source.startswith("gmail"))
        )
    ).scalars().all()

    by_rule: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_conf: dict[str, int] = {"high": 0, "mid": 0, "low": 0}
    llm_count = 0
    rule_count = 0

    for tx in rows:
        tags = tx.llm_tags or {}
        rule = tags.get("rule") or "unknown"
        by_rule[rule] = by_rule.get(rule, 0) + 1
        by_status[tx.status] = by_status.get(tx.status, 0) + 1
        if rule == "llm-fallback":
            llm_count += 1
        else:
            rule_count += 1
        c = tx.confidence or 0.0
        if c >= 0.9:
            by_conf["high"] += 1
        elif c >= 0.7:
            by_conf["mid"] += 1
        else:
            by_conf["low"] += 1

    return IngestStats(
        total=len(rows),
        by_rule=by_rule,
        by_status=by_status,
        by_confidence=by_conf,
        llm_fallback_count=llm_count,
        rule_count=rule_count,
    )


async def _run_sync_bg(query: str | None) -> None:
    """Run one poll in a fresh DB session — safe for BackgroundTasks (the
    request-scoped session is closed before this runs)."""
    global _last_result, _running
    if _sync_lock.locked():
        log.info("gmail sync skipped: another sync is already running")
        return
    async with _sync_lock:
        _running = True
        try:
            async with SessionLocal() as session:
                try:
                    r = await poll_once(session, query=query)
                    _last_result = {
                        "ok": r.ok,
                        "processed": r.processed,
                        "ingested": r.ingested,
                        "skipped": r.skipped,
                        "errors": r.errors,
                        "marked_read": r.marked_read,
                        "llm_fallback_used": r.llm_fallback_used,
                        "history_id": r.history_id,
                        "message": r.message,
                        "finished_at": datetime.utcnow().isoformat(),
                    }
                except Exception as e:
                    log.exception("gmail bg sync crashed")
                    _last_result = {
                        "ok": False,
                        "processed": 0,
                        "ingested": 0,
                        "skipped": 0,
                        "errors": 1,
                        "marked_read": 0,
                        "llm_fallback_used": 0,
                        "history_id": None,
                        "message": f"crash: {type(e).__name__}: {e}",
                        "finished_at": datetime.utcnow().isoformat(),
                    }
        finally:
            _running = False


@router.post("/sync", response_model=GmailSyncResult)
async def sync_now(
    background_tasks: BackgroundTasks,
    query: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Kick off one sync iteration in the background and return immediately.

    Gmail sync can take 1–2 minutes (LLM fallback per email), longer than the
    Next.js rewrite proxy's 30s timeout. Returning a 202-style response lets
    the UI show a toast and poll `/gmail/sync/status` for the final result.

    `query` overrides the default filter `is:unread in:inbox newer_than:7d`.
    """
    if _running:
        return GmailSyncResult(
            ok=True,
            processed=0,
            ingested=0,
            skipped=0,
            errors=0,
            marked_read=0,
            llm_fallback_used=0,
            history_id=None,
            message="sync already running — poll /gmail/sync/status",
        )
    background_tasks.add_task(_run_sync_bg, query)
    return GmailSyncResult(
        ok=True,
        processed=0,
        ingested=0,
        skipped=0,
        errors=0,
        marked_read=0,
        llm_fallback_used=0,
        history_id=None,
        message="started — poll /gmail/sync/status for result",
    )


@router.get("/sync/status")
async def sync_status():
    """Return current sync state: running flag + last completed run's stats.
    UI polls this every few seconds after kicking off a sync."""
    return {
        "running": _running,
        "last_result": _last_result,
    }
