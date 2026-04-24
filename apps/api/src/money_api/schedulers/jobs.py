"""APScheduler wiring.

Runs Gmail poll at a fixed interval. Guarded by feature flag env
(polling only runs if connected; otherwise the job is a no-op).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import get_settings
from ..db import SessionLocal
from ..ingest.gmail_poller import poll_once
from ..services.backup import prune_backups, run_backup

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _job_gmail_poll() -> None:
    async with SessionLocal() as session:
        r = await poll_once(session)
        if not r.ok:
            log.info("gmail poll: %s", r.message)
        else:
            log.info(
                "gmail poll ok processed=%d ingested=%d skipped=%d errors=%d hist=%s",
                r.processed,
                r.ingested,
                r.skipped,
                r.errors,
                r.history_id,
            )


async def _job_daily_backup() -> None:
    try:
        b = await run_backup()
        log.info("daily backup: %s (%.1f KB)", b.name, b.size_bytes / 1024)
    except Exception as e:
        log.error("daily backup failed: %s", e)
    try:
        removed = await prune_backups()
        if removed:
            log.info("pruned %d old backup file(s)", removed)
    except Exception as e:
        log.warning("prune failed: %s", e)


def _parse_hours(raw: str) -> list[int]:
    """Parse '8,20' → [8, 20]. Ignore invalid entries. Return empty list when
    disabled (empty string)."""
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h = int(part)
        except ValueError:
            log.warning("ignored invalid gmail_sync_hours entry: %r", part)
            continue
        if 0 <= h <= 23:
            out.append(h)
        else:
            log.warning("ignored out-of-range hour: %d", h)
    return sorted(set(out))


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    s = get_settings()
    sched = AsyncIOScheduler(timezone=s.tz)

    hours = _parse_hours(s.gmail_sync_hours)
    if hours:
        # Cron mode: run at exactly these hours each day (e.g. 8:00 + 20:00 local).
        sched.add_job(
            _job_gmail_poll,
            trigger="cron",
            hour=",".join(str(h) for h in hours),
            minute=0,
            id="gmail_poll",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        sched_desc = f"gmail_poll daily at {hours} {s.tz}"
    else:
        # Legacy interval fallback when GMAIL_SYNC_HOURS is explicitly empty.
        sched.add_job(
            _job_gmail_poll,
            trigger="interval",
            seconds=s.gmail_poll_interval_sec,
            id="gmail_poll",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        sched_desc = f"gmail_poll every {s.gmail_poll_interval_sec}s"

    # Daily backup at 02:00 local time (unchanged).
    sched.add_job(
        _job_daily_backup,
        trigger="cron",
        hour=2,
        minute=0,
        id="daily_backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    log.info(
        "scheduler started: %s, daily_backup at 02:00 %s",
        sched_desc,
        s.tz,
    )
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
