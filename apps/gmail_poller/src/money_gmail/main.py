"""Gmail poller — idles gracefully if OAuth not configured yet.

In a next milestone this will:
  1. Load refresh_token from API (encrypted), refresh access_token.
  2. Call history.list since last_history_id.
  3. For each new message, call /api/v1/ingest/gmail on core API.
  4. Persist new history_id via /api/v1/settings or sync_state endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("money_gmail")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")


async def main() -> None:
    interval = int(os.environ.get("GMAIL_POLL_INTERVAL_SEC", "600"))
    target = os.environ.get("GMAIL_TARGET_EMAIL", "")
    log.info("gmail poller up, target=%s, interval=%ss (idle until OAuth wired)", target, interval)
    while True:
        # TODO M4: call API /oauth/google/status. If not connected → idle.
        # If connected → history.list, ingest each message.
        await asyncio.sleep(interval)
