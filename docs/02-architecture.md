# 02 — Kiến trúc hệ thống

## Sơ đồ tổng thể

```mermaid
flowchart TB
    subgraph Client
        UI[Next.js Web UI]
        TG[Telegram App]
    end

    subgraph Server["Local machine (Docker compose)"]
        API[FastAPI<br/>REST + WS]
        BOT[Telegram Bot Worker<br/>polling 5s]
        GM[Gmail Poller<br/>cron 10min]
        SCH[Scheduler<br/>APScheduler]
        LLM[LLM Router]
        DB[(SQLite)]
    end

    subgraph External
        OLL[Ollama<br/>localhost:11434]
        DS[DeepSeek API<br/>optional]
        GAPI[Gmail API]
        TAPI[Telegram Bot API]
    end

    UI -->|HTTPS| API
    TG <-->|Bot API| TAPI
    TAPI <-->|getUpdates 5s| BOT

    BOT --> API
    GM --> API
    SCH --> API

    API --> LLM
    API --> DB
    LLM --> OLL
    LLM -.redacted.-> DS
    GM -->|OAuth| GAPI
    SCH --> BOT
```

## Các thành phần

### 1. Web UI — Next.js
- Dashboard, danh sách giao dịch, form nhập tay, chat UI, cấu hình.
- Giao tiếp backend qua REST (CRUD) + WebSocket (streaming chat LLM, notify live).
- Chạy trên `:3000`.

### 2. API — FastAPI
- Lớp HTTP duy nhất. Mọi input đều đi qua đây.
- Chịu trách nhiệm validate, dedupe, lưu DB, gọi LLM.
- Expose REST + WS. Tham khảo [09-api.md](./09-api.md).
- Chạy trên `:8000`.

### 3. Telegram Bot Worker
- Process riêng, short polling `getUpdates` mỗi **5 giây**.
- Không cần domain/HTTPS. Xem chi tiết trong [08-telegram.md](./08-telegram.md).
- Không xử lý business logic — forward sang API qua HTTP nội bộ.

### 4. Gmail Poller
- Process riêng, chạy mỗi 10 phút (configurable).
- Dùng `historyId` để incremental sync, chỉ kéo email mới.
- Parse qua pipeline 2 tầng (regex → LLM). Xem [07-gmail.md](./07-gmail.md).

### 5. Scheduler
- APScheduler trong cùng process với API (hoặc tách nếu cần).
- Job định kỳ: tổng kết tuần/tháng, nhắc nhập liệu, backup DB.

### 6. LLM Router
- Module trong API, không phải service riêng.
- Quyết định dùng Ollama hay DeepSeek dựa trên task + độ nhạy cảm của input.
- Xem [06-llm-strategy.md](./06-llm-strategy.md).

### 7. Database — SQLite
- Single file `data/money.db`.
- Đủ cho 1 user, tránh overhead Postgres.
- Migrate qua Alembic.

## Luồng dữ liệu chính

### A. Nhập giao dịch qua chat (web hoặc Telegram)

```mermaid
sequenceDiagram
    actor User
    participant Client as Web/Telegram
    participant API
    participant LLM
    participant DB

    User->>Client: "ăn phở 45k bằng momo"
    Client->>API: POST /chat {text}
    API->>DB: load accounts, categories, recent_merchants
    API->>LLM: extract_transaction(text, context)
    LLM-->>API: JSON {amount, account, category, merchant, ts, confidence}
    alt confidence >= 0.8
        API->>DB: INSERT transaction (status=pending)
        API-->>Client: card confirm
        User->>Client: ✅ Đúng
        Client->>API: POST /transactions/:id/confirm
        API->>DB: UPDATE status=confirmed
    else confidence < 0.8
        API-->>Client: hỏi rõ thêm (account? amount?)
    end
```

### B. Nhập từ Gmail

```mermaid
sequenceDiagram
    participant Cron as Gmail Poller
    participant GAPI as Gmail API
    participant API
    participant LLM
    participant DB

    Cron->>GAPI: history.list(startHistoryId)
    GAPI-->>Cron: new message IDs
    loop mỗi message
        Cron->>GAPI: messages.get(id)
        GAPI-->>Cron: email body
        Cron->>API: POST /ingest/gmail {msg}
        API->>DB: match rule by sender+subject
        alt có rule
            API->>API: regex extract
        else không rule
            API->>LLM: extract (redacted)
            LLM-->>API: JSON
            API->>DB: propose new rule
        end
        API->>DB: dedupe + INSERT transaction
        API->>TG: notify nếu cần confirm
    end
    Cron->>DB: save new historyId
```

### C. Cảnh báo budget

```mermaid
sequenceDiagram
    participant API
    participant DB
    participant TG as Telegram

    Note over API: sau mỗi INSERT transaction
    API->>DB: SELECT SUM by category, month
    alt vượt 80% budget
        API->>TG: notify "Ăn uống: 2.4M/3M (80%)"
    end
```

## Tách process & chạy song song

| Process | Vai trò | Scale |
|---|---|---|
| `api` | REST + WS + Scheduler | 1 instance |
| `web` | Next.js | 1 instance |
| `bot` | Telegram polling | 1 instance (tránh trùng offset) |
| `gmail` | Gmail polling | 1 instance |
| `ollama` | LLM local | 1 instance (nặng RAM) |

Không cần queue ở MVP vì throughput thấp (< 100 giao dịch/ngày). Khi cần thì thêm Redis + RQ.

## State & persistence

| State | Lưu ở đâu |
|---|---|
| Giao dịch, category, budget, rule | SQLite |
| Gmail `historyId`, Telegram `update_id` offset | bảng `sync_state` trong SQLite |
| LLM prompt/response log (debug) | file `logs/llm.jsonl` |
| OAuth refresh token | bảng `oauth_credentials` (mã hoá) |
| User preferences (UI) | bảng `settings` |

Backup: dump SQLite hàng đêm ra `backups/money-YYYYMMDD.db`, giữ 30 ngày.
