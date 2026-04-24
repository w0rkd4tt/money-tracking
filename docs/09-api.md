# 09 — API spec

REST API do FastAPI cung cấp. Cổng mặc định `:8000`. WebSocket cho streaming chat & live update.

## Convention

- Base: `http://localhost:8000/api/v1`
- Auth: local-only, không cần token (bind `127.0.0.1`). Nếu mở ra LAN → bật basic token header `X-API-Key`.
- Content: `application/json`, timezone trả về luôn có TZ offset.
- Amount trả về là số nguyên VND (mặc định). Nếu cần currency khác, kèm `currency`.
- Error: RFC 7807 problem+json.

## Endpoints

### Auth & setup

| Method | Path | Mô tả |
|---|---|---|
| GET | `/oauth/google/start` | Sinh URL consent Google |
| GET | `/oauth/google/callback` | Callback Google, lưu credential |
| DELETE | `/oauth/google` | Disconnect Gmail |
| GET | `/health` | Liveness |
| GET | `/info` | Version, model loaded, DB path |

### Accounts

| Method | Path | Body | Mô tả |
|---|---|---|---|
| GET | `/accounts` | — | List accounts |
| POST | `/accounts` | `{name,type,currency,opening_balance}` | Tạo |
| PATCH | `/accounts/:id` | partial | Sửa |
| DELETE | `/accounts/:id` | — | Archive (soft) |
| GET | `/accounts/balance` | — | Số dư tất cả account |

### Categories

| Method | Path | Mô tả |
|---|---|---|
| GET | `/categories` | Trả cây phẳng |
| GET | `/categories/tree` | Trả cấu trúc lồng |
| POST | `/categories` | `{name,parent_id?,kind,icon?,color?}` |
| PATCH | `/categories/:id` | |
| DELETE | `/categories/:id` | Chỉ xoá được khi không có transaction |

### Transactions

| Method | Path | Query / Body | Mô tả |
|---|---|---|---|
| GET | `/transactions` | `?from&to&account_id&category_id&status&q&page&size` | Danh sách, phân trang |
| GET | `/transactions/:id` | — | Chi tiết |
| POST | `/transactions` | `{ts,amount,account_id,category_id,merchant?,note?,source?}` | Manual insert |
| PATCH | `/transactions/:id` | partial | Sửa |
| POST | `/transactions/:id/confirm` | — | Đổi status pending → confirmed |
| POST | `/transactions/:id/reject` | — | pending → rejected (soft delete) |
| DELETE | `/transactions/:id` | — | Hard delete (nếu < 5 phút) |
| DELETE | `/transactions/last` | — | Undo giao dịch mới nhất |
| GET | `/transactions/stats` | `?group_by=category&period=month` | Aggregate |

**Schema `POST /transactions`:**
```json
{
  "ts": "2026-04-21T12:30:00+07:00",
  "amount": -45000,
  "currency": "VND",
  "account_id": 2,
  "category_id": 15,
  "merchant": "Quán phở",
  "note": "trưa",
  "source": "manual"
}
```

### Chat

| Method | Path | Mô tả |
|---|---|---|
| POST | `/chat/message` | Gửi message, nhận extract |
| GET | `/chat/sessions` | List session |
| GET | `/chat/sessions/:id/messages` | History |
| DELETE | `/chat/sessions/:id` | Xoá session |

**Schema `POST /chat/message`:**
```json
// request
{ "channel":"web","external_id":"sess-uuid","text":"trưa cafe 30k" }

// response
{
  "intent": "create_transaction" | "query" | "unknown",
  "transactions": [
    {
      "id": 123, "status": "pending",
      "preview": {
        "ts": "...", "amount": -30000, "account": "Tiền mặt",
        "category": "Ăn uống > Sáng", "merchant": "cafe"
      },
      "confidence": 0.82,
      "ambiguous_fields": ["category"]
    }
  ],
  "reply_text": "Xác nhận 2 giao dịch này nhé?",
  "follow_up_questions": []
}
```

### Budgets

| Method | Path | Mô tả |
|---|---|---|
| GET | `/budgets` | List |
| POST | `/budgets` | `{category_id,period,limit_amount,rollover}` |
| PATCH | `/budgets/:id` | |
| DELETE | `/budgets/:id` | |
| GET | `/budgets/status` | `?period=2026-04` — % used mỗi category |

### Rules

| Method | Path | Mô tả |
|---|---|---|
| GET | `/rules` | List |
| POST | `/rules` | Tạo rule |
| PATCH | `/rules/:id` | Sửa / enable / disable |
| DELETE | `/rules/:id` | |
| POST | `/rules/:id/test` | `{sample}` — chạy thử regex |
| POST | `/rules/suggest/approve` | Duyệt rule do LLM đề xuất |

### Merchants

| Method | Path | Mô tả |
|---|---|---|
| GET | `/merchants` | `?q=` search |
| POST | `/merchants` | Tạo canonical |
| POST | `/merchants/:id/merge` | `{alias_ids:[]}` gộp alias |
| PATCH | `/merchants/:id` | |

### Tags

| Method | Path | Mô tả |
|---|---|---|
| GET | `/tags` | |
| POST | `/tags` | |
| POST | `/transactions/:id/tags` | `{tag_ids:[]}` gắn nhiều |
| DELETE | `/transactions/:id/tags/:tag_id` | |

### Ingest (internal)

| Method | Path | Mô tả |
|---|---|---|
| POST | `/ingest/gmail` | Body = Gmail message object. Gọi từ gmail poller process. |
| POST | `/ingest/telegram` | Body = normalized message. Gọi từ bot worker. |

Các endpoint này bị block từ public — chỉ cho `127.0.0.1` hoặc docker network nội bộ.

### Reports

| Method | Path | Mô tả |
|---|---|---|
| GET | `/reports/weekly` | `?week=2026-W17` — Trả digest đã sinh (hoặc kích sinh) |
| GET | `/reports/monthly` | `?month=2026-04` |
| GET | `/export/csv` | `?from&to` — Stream CSV |

### Settings

| Method | Path | Mô tả |
|---|---|---|
| GET | `/settings` | |
| PATCH | `/settings` | |

Key settings đáng kể: `default_account_id`, `llm.allow_cloud`, `llm.monthly_budget_usd`, `llm.agent_enabled`, `llm.gmail_tool_enabled`, `notify.budget_thresholds`, `locale`, `timezone`.

### LLM tool policies & audit

| Method | Path | Mô tả |
|---|---|---|
| GET | `/llm/policies/gmail` | List allow/deny patterns |
| POST | `/llm/policies/gmail` | Thêm `{action, pattern_type, pattern, priority, note}` |
| PATCH | `/llm/policies/gmail/:id` | Enable/disable, sửa |
| DELETE | `/llm/policies/gmail/:id` | Xoá |
| POST | `/llm/policies/gmail/test` | `{query}` → trả rewritten query + preview matched senders |
| GET | `/llm/audit` | `?tool=&from=&to=&status=` — audit log tool call |
| GET | `/llm/audit/:id` | Chi tiết 1 call |
| GET | `/llm/traces/:session_id` | Redirect tới Langfuse trace (nếu enabled) |
| GET | `/llm/agent/health` | Ping agent model + tools, check provider alive |

## WebSocket

### `/ws/chat/:session_id`
- Stream chunk từ LLM khi đang generate.
- Event types:
  - `{"type":"partial","text":"..."}`
  - `{"type":"extracted","transactions":[...]}`
  - `{"type":"done"}`
  - `{"type":"error","message":"..."}`

### `/ws/live`
- Push sự kiện live cho UI:
  - `transaction.created` / `updated` / `deleted`
  - `budget.threshold_crossed`
  - `gmail.new_message`
  - `notification`

## Pagination

Mặc định `page=1&size=50`, max `size=200`. Response:

```json
{
  "items": [...],
  "total": 1234,
  "page": 1,
  "size": 50,
  "has_next": true
}
```

## Error format

```json
{
  "type": "/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "detail": "amount must be != 0",
  "instance": "/transactions",
  "fields": {"amount": ["Must be non-zero integer"]}
}
```

Mã thường dùng: `400 bad_request`, `401 unauthorized` (nếu bật X-API-Key), `403 forbidden_source`, `404 not_found`, `409 duplicate`, `422 validation`, `429 rate_limited`, `500 internal`.

## Rate limit

Local-only nên MVP không cần. Nếu mở ra LAN: 60 req/min/IP cho `/chat/*`, 300 req/min cho GET còn lại.

## Versioning

- Prefix `/api/v1` cố định cho MVP.
- Breaking change → `/api/v2` song song.
- OpenAPI schema tự sinh tại `/api/v1/openapi.json`, Swagger UI `/api/v1/docs`.
