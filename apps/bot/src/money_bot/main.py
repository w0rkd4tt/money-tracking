"""Telegram bot — short polling 5s, forwards messages to core API."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

log = logging.getLogger("money_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")


class Settings:
    bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_chat_ids: set[int] = {
        int(x) for x in os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if x.strip().isdigit()
    }
    poll_interval: int = int(os.environ.get("TELEGRAM_POLL_INTERVAL_SEC", "5"))
    api_url: str = os.environ.get("API_URL", "http://api:8000/api/v1").rstrip("/")
    tg_base: str = ""

    def __post_init__(self) -> None:
        self.tg_base = f"https://api.telegram.org/bot{self.bot_token}"


S = Settings()
S.tg_base = f"https://api.telegram.org/bot{S.bot_token}" if S.bot_token else ""

HELP_TEXT = (
    "🤖 Money bot commands:\n"
    "/today – giao dịch hôm nay\n"
    "/week – tuần này\n"
    "/month – tháng này\n"
    "/balance – số dư mỗi account\n"
    "/last – giao dịch mới nhất\n"
    "/budget – status ngân sách\n"
    "/help"
)


async def _tg(client: httpx.AsyncClient, method: str, **params: Any) -> dict:
    r = await client.get(f"{S.tg_base}/{method}", params=params)
    return r.json()


async def _tg_post(client: httpx.AsyncClient, method: str, json: dict) -> dict:
    r = await client.post(f"{S.tg_base}/{method}", json=json)
    return r.json()


async def send(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    await _tg_post(client, "sendMessage", {"chat_id": chat_id, "text": text})


async def handle_command(
    client: httpx.AsyncClient, api: httpx.AsyncClient, chat_id: int, text: str
) -> None:
    cmd = text.split()[0].lower()
    if cmd == "/start" or cmd == "/help":
        await send(client, chat_id, HELP_TEXT)
        return
    if cmd == "/balance":
        try:
            r = await api.get("/accounts/balance")
            rows = r.json()
            lines = [f"{b['name']}: {int(float(b['balance'])):,} {b['currency']}" for b in rows]
            await send(client, chat_id, "💰 Số dư:\n" + "\n".join(lines))
        except Exception as e:
            await send(client, chat_id, f"Lỗi: {e}")
        return
    if cmd == "/last":
        try:
            r = await api.get("/transactions/last")
            t = r.json()
            await send(
                client,
                chat_id,
                f"Giao dịch mới nhất: {t['amount']} {t['currency']} — {t.get('note') or t.get('merchant_text') or ''}",
            )
        except Exception as e:
            await send(client, chat_id, f"Lỗi: {e}")
        return
    if cmd == "/budget":
        try:
            r = await api.get("/budgets/status")
            rows = r.json()
            if not rows:
                await send(client, chat_id, "Chưa có budget nào.")
                return
            lines = [
                f"{b.get('category_name') or 'Tổng'}: {int(float(b['pct']))}% ({int(float(b['spent'])):,}/{int(float(b['limit_amount'])):,})"
                for b in rows
            ]
            await send(client, chat_id, "📊 Budget:\n" + "\n".join(lines))
        except Exception as e:
            await send(client, chat_id, f"Lỗi: {e}")
        return
    await send(client, chat_id, f"Chưa hỗ trợ lệnh: {cmd}\n{HELP_TEXT}")


async def handle_chat(
    client: httpx.AsyncClient, api: httpx.AsyncClient, chat_id: int, text: str
) -> None:
    try:
        r = await api.post(
            "/chat/message",
            json={"channel": "telegram", "external_id": str(chat_id), "text": text},
        )
        data = r.json()
        msg = data.get("reply_text", "Đã xử lý.")
        txs = data.get("transactions") or []
        for t in txs:
            if t.get("id"):
                msg += f"\n#{t['id']} • {t['amount']} {t.get('currency','VND')} • {t.get('category') or '—'} (pending)"
        await send(client, chat_id, msg)
    except Exception as e:
        await send(client, chat_id, f"Chat lỗi: {e}")


async def handle_update(
    client: httpx.AsyncClient, api: httpx.AsyncClient, upd: dict
) -> None:
    msg = upd.get("message") or {}
    chat = (msg.get("chat") or {})
    chat_id = chat.get("id")
    if chat_id is None:
        return
    if S.allowed_chat_ids and chat_id not in S.allowed_chat_ids:
        log.warning("Ignored unauthorized chat_id=%s", chat_id)
        return
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text.startswith("/"):
        await handle_command(client, api, chat_id, text)
    else:
        await handle_chat(client, api, chat_id, text)


async def run() -> None:
    if not S.bot_token:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot is idle. Set it and restart.")
        while True:
            await asyncio.sleep(3600)
    log.info("bot up, interval=%ss, whitelist=%s", S.poll_interval, S.allowed_chat_ids or "<empty>")
    offset = 0
    async with httpx.AsyncClient(timeout=15) as client, httpx.AsyncClient(
        base_url=S.api_url, timeout=30
    ) as api:
        while True:
            try:
                data = await _tg(
                    client,
                    "getUpdates",
                    offset=offset,
                    timeout=0,
                    allowed_updates='["message"]',
                    limit=100,
                )
                for u in data.get("result") or []:
                    offset = u["update_id"] + 1
                    await handle_update(client, api, u)
            except Exception as e:
                log.error("poll error: %s", e)
            await asyncio.sleep(S.poll_interval)


async def main() -> None:
    await run()
