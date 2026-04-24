# 08 — Telegram bot

## Mục tiêu

Biến Telegram thành "giao diện di động" cho app. User chat như với web, nhận thông báo, confirm giao dịch, hỏi nhanh số liệu.

## Thiết kế chung

- **Không dùng webhook** — không cần domain/HTTPS/ngrok.
- **Short polling** gọi `getUpdates` mỗi **5 giây** (theo yêu cầu user).
- 1 bot token, 1 chat_id owner duy nhất trong whitelist (`TELEGRAM_ALLOWED_CHAT_IDS`).
- Bot worker là process riêng (`apps/bot`), forward business logic vào API HTTP nội bộ (`http://api:8000`).

### Ghi chú về long polling (không bắt buộc dùng)

Telegram hỗ trợ `getUpdates?timeout=N` (long polling). Đây **không** phải webhook — client vẫn chủ động gọi API, không cần domain. So với short polling 5s: ít request hơn ~100 lần, độ trễ ~1s thay vì 0–5s. Nếu sau này muốn tối ưu, đổi sang long polling chỉ là đổi 1 param, không ảnh hưởng kiến trúc.

Tài liệu này mô tả **short polling 5s** như chọn lựa hiện tại.

## Polling loop

### Pseudo-code

```python
import asyncio, httpx

API_BASE = f"https://api.telegram.org/bot{TOKEN}"
POLL_INTERVAL = 5  # giây

async def run():
    offset = load_offset_from_db()  # sync_state['telegram.update_offset']
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                r = await client.get(
                    f"{API_BASE}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 0,       # short polling: return ngay
                        "allowed_updates": ["message","callback_query"],
                        "limit": 100,
                    },
                )
                r.raise_for_status()
                updates = r.json()["result"]
            except Exception as e:
                log.error("poll failed", exc_info=e)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            for u in updates:
                offset = u["update_id"] + 1
                await handle_update(u)
            save_offset_to_db(offset)

            await asyncio.sleep(POLL_INTERVAL)
```

### Đặc điểm cần chú ý

1. **Offset phải tăng chặt** (`last_update_id + 1`), nếu không sẽ nhận lặp.
2. **Persist offset** qua restart — lưu vào `sync_state` DB. Nếu mất offset, sau restart sẽ xử lý lại 24h gần nhất (Telegram giữ update 24h).
3. **1 instance bot duy nhất** — Telegram không cho 2 poller dùng cùng token (mỗi call getUpdates "khoá" các update cũ cho instance khác). Docker compose cấu hình `replicas: 1`.
4. **Xử lý update song song an toàn**: trong 1 batch có thể có nhiều update, xử lý tuần tự hoặc dùng `asyncio.gather` với chú ý ordering (khi user gửi nhiều tin liên tiếp). Đơn giản: tuần tự.

### Budget request

| Thành phần | Giá trị |
|---|---|
| Interval | 5s |
| Request/ngày | 86400 / 5 = 17.280 |
| Với Telegram free tier | không giới hạn hợp lý, thoải mái |
| Latency cảm nhận | 0–5s (trung bình 2.5s) |

Không vấn đề gì với 1 user. Nếu cảm thấy 2.5s trễ khó chịu khi chat → đổi `POLL_INTERVAL = 2` hoặc chuyển long polling.

## Xử lý update

```python
async def handle_update(u: dict):
    if "message" in u:
        await handle_message(u["message"])
    elif "callback_query" in u:
        await handle_callback(u["callback_query"])

async def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    if chat_id not in ALLOWED:
        return  # im lặng drop
    text = msg.get("text", "")
    if text.startswith("/"):
        await handle_command(chat_id, text)
    else:
        await handle_chat(chat_id, text)
```

### Whitelist
- `TELEGRAM_ALLOWED_CHAT_IDS` trong env (comma-separated).
- Update từ chat_id khác → log warn, không reply (tránh leak info).

## Commands

| Lệnh | Mô tả | Tương đương API |
|---|---|---|
| `/start` | Intro, gắn chat_id vào whitelist (one-time setup) | — |
| `/today` | Liệt kê giao dịch hôm nay | `GET /transactions?date=today` |
| `/yesterday` | Hôm qua | — |
| `/week` | Chi tiêu 7 ngày gần nhất | — |
| `/month` | Tổng kết tháng hiện tại | — |
| `/budget` | Trạng thái budget theo category | `GET /budgets/status` |
| `/balance` | Số dư mỗi account | `GET /accounts/balance` |
| `/last` | 5 giao dịch gần nhất | — |
| `/undo` | Xoá giao dịch vừa thêm (trong 5 phút) | `DELETE /transactions/last` |
| `/pending` | List giao dịch đang chờ confirm | `GET /transactions?status=pending` |
| `/cancel` | Huỷ context chat hiện tại | — |
| `/help` | Hiện list commands | — |

## Chat tự do

Khi `text` không phải command, forward vào API chat endpoint:

```
POST /chat/message
{
  "channel": "telegram",
  "external_id": "<chat_id>",
  "text": "trưa nay ăn phở 45k bằng momo"
}

Response:
{
  "intent": "create_transaction",
  "transactions": [
    { "id": 123, "status": "pending", "preview": {...} }
  ],
  "reply_text": "Xác nhận giao dịch này nhé?"
}
```

Bot format response thành card với inline keyboard:

```
💸 −45.000 đ • Momo
🍜 Ăn uống > Trưa
"quán phở" • 21/04 12:30

[✓ Đúng] [✎ Sửa] [🏷 Đổi loại] [✗ Huỷ]
```

## Inline keyboard callback

Callback data format: `<action>:<tx_id>[:arg]`.

| Action | Ví dụ | Xử lý |
|---|---|---|
| `confirm` | `confirm:123` | `POST /transactions/123/confirm` |
| `reject` | `reject:123` | `DELETE /transactions/123` |
| `edit` | `edit:123` | Reply "gửi cho tôi câu sửa (vd: '50k chứ không phải 45k')" |
| `recat` | `recat:123` | Hiện keyboard chọn category |
| `setcat` | `setcat:123:An-uong>Trua` | Update category |

Phản hồi nhanh bằng `answerCallbackQuery` (< 200ms) sau đó edit message.

## Notify outgoing

Bot không chỉ reply — API cũng chủ động push:

```python
# Từ API process (tách khỏi bot worker):
async def notify(chat_id: int, text: str, kb: dict = None):
    await httpx.post(f"{API_BASE}/sendMessage", json={
        "chat_id": chat_id, "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": kb,
    })
```

Các trigger notify:
- Giao dịch mới từ Gmail cần confirm.
- Vượt ngưỡng budget (50/80/100/120%).
- Weekly digest Chủ nhật 20:00.
- Monthly summary ngày 1.
- Giao dịch bất thường (amount > P95, merchant lạ).

### Dedup notify

Cùng 1 event không notify 2 lần (trừ khi user yêu cầu nhắc lại):

```
notify_log (event_key, sent_at)
event_key ví dụ: "budget:category=5:month=2026-04:threshold=80"
```

## Format text

Dùng MarkdownV2, cần escape `_*[]()~\`>#+-=|{}.!`. Viết util `md_escape()`.

Amount format: `1\.234\.567 đ` (có dấu chấm nghìn, escape dấu chấm).

## Session chat

- Mỗi chat_id có 1 `chat_session` trong DB.
- Giữ 10 message gần nhất làm context cho LLM (như web).
- `/cancel` xoá session.

## Voice / ảnh (phase 2)

- **Voice message**: download OGG, dùng Whisper (qua Ollama có `faster-whisper` wrapper) → text → same flow.
- **Ảnh hoá đơn**: VLM (`qwen2-vl`) → OCR + extract giao dịch.

## Bảo mật

- Bot token chỉ trong `.env`, không commit.
- Whitelist chat_id bắt buộc (bot public bị spam cũng không sao).
- Không log full message content ra file (có thể chứa thông tin nhạy cảm nếu user paste email). Log chỉ `update_id`, `chat_id`, `type`, length.
- Token rotation: nếu nghi lộ → `BotFather` → revoke → cập nhật env → restart bot.

## Quản lý process

- Service `bot` trong docker-compose, `restart: unless-stopped`.
- Healthcheck: gọi `getMe` mỗi phút, fail 3 lần liên tiếp → restart.
- Log: JSON line, có trace_id liên kết với API.

## Testing

- Mock Telegram API bằng httpx transport → test polling loop.
- E2E: gửi thủ công bằng bot test → assert DB có transaction đúng.
- Test edge:
  - User gửi nhiều tin trong < 5s → batch xử lý đúng thứ tự.
  - Bot restart → không bị lặp update (offset persist).
  - Telegram API 502 → retry backoff, không crash.
