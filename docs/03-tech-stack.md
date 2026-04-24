# 03 — Tech stack

## Tổng quan

| Layer | Công nghệ | Phiên bản tham khảo |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript | 15.x |
| UI kit | shadcn/ui + TailwindCSS | latest |
| Chart | Recharts | 2.x |
| Backend | FastAPI + Python | 3.12, FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 + Alembic | — |
| DB | SQLite (WAL mode) | 3.40+ |
| LLM local (provider `m1ultra`) | Ollama native trên host M1 Ultra | latest |
| LLM model chính | `jaahas/qwen3.5-uncensored:9b` | — |
| LLM agent model | `qwen2.5:7b-instruct` (tool calling chắc cú) | — |
| LLM cloud (optional) | DeepSeek API | v3 / chat |
| Embedding | `nomic-embed-text` qua Ollama | — |
| Agent framework | **LangChain + LangGraph** (`create_react_agent`) | latest |
| Observability | **Langfuse** (self-host v2, hoặc cloud opt-in) | v2 |
| Vector store | `sqlite-vec` extension | — |
| Telegram | `python-telegram-bot` hoặc httpx raw | v21+ |
| Gmail | `google-api-python-client` + `google-auth-oauthlib` | — |
| Scheduler | APScheduler | 3.x |
| Validation | Pydantic v2 | — |
| Package mgr | `uv` (Python), `pnpm` (JS) | — |
| Container | Docker Compose v2 | — |

## Lý do chọn

### FastAPI (Python) thay vì Node
- Hệ sinh thái Python mạnh nhất cho LLM, Gmail API client, parsing PDF/HTML.
- Pydantic v2 + OpenAPI tự sinh giúp contract frontend-backend rõ ràng.
- Async native, đủ cho throughput của 1 user.

### Next.js thay vì Vite SPA
- SSR cho dashboard load nhanh, SEO không quan trọng nhưng cache tốt.
- App Router + Server Components giảm lượng JS client.
- Deploy tĩnh cũng được nếu không cần SSR (`output: "export"`).

### SQLite thay vì Postgres
- 1 user, throughput thấp. Postgres là over-engineering.
- File-based → backup chỉ cần copy file.
- WAL mode cho concurrent read/write tốt.
- Khi cần scale (multi-user) đổi sang Postgres bằng cách đổi `DATABASE_URL` và rerun migration.

### Ollama thay vì gọi trực tiếp llama.cpp
- CLI/HTTP API sạch, model pull đơn giản.
- Hỗ trợ structured output (`format: "json"`) và tool calling từ các model mới.
- Quản lý nhiều model song song dễ.
- Chạy **native trên host macOS** để tận dụng Metal GPU, không bọc container.

### Provider `m1ultra` — Ollama chạy native trên host

Đây là **named provider** trong LLM Router, trỏ tới Ollama chạy trực tiếp trên máy user (M1 Ultra). Lý do đặt tên riêng thay vì `ollama`:
- Tách bạch rõ ràng với các provider khác (cloud, hoặc tương lai thêm máy Ollama khác qua LAN).
- Config có thể khác nhau giữa các instance (model, timeout, URL).
- Dễ mở rộng sau này (vd: thêm `m2pro`, `homeserver`…).

**Config từ .env:**
```
LLM_DEFAULT_PROVIDER=m1ultra
M1ULTRA_URL=http://127.0.0.1:11434   # đổi → host.docker.internal:11434 nếu chạy Docker
M1ULTRA_MODEL=jaahas/qwen3.5-uncensored:9b
M1ULTRA_TIMEOUT=120
M1ULTRA_EMBED_MODEL=nomic-embed-text
```

**Vì sao uncensored model?**
- Giao dịch tài chính cá nhân không cần safety filter khắt khe (đa số filter từ chối là không cần thiết cho task extract).
- Model uncensored 9B thường theo instruction tốt hơn, ít "từ chối vô cớ" khi parse email lạ hoặc tên merchant nhạy cảm (bar, game, etc.).
- Nếu muốn đổi lại: chỉ cần `M1ULTRA_MODEL=qwen2.5:7b-instruct` trong .env, không đụng code.

**Tại sao Ollama native thay vì container?**
- Metal GPU passthrough vào Docker trên macOS không có → chạy container sẽ CPU-only, chậm 5–10 lần.
- Ollama native macOS tận dụng Metal tốt, model 9B inference ~30–60 tokens/s trên M1 Ultra.

### Model đề xuất cho `m1ultra`

| Use case | Model | RAM | Ghi chú |
|---|---|---|---|
| Extract giao dịch (chính) | `jaahas/qwen3.5-uncensored:9b` | ~9GB | Default |
| Extract nhẹ (alt) | `qwen2.5:7b-instruct` | ~6GB | Safety filter mặc định |
| Classify category | cùng model + prompt ngắn, hoặc kNN | — | Ưu tiên kNN trước |
| Embedding | `nomic-embed-text` | ~500MB | Semantic search, classify |
| Vision (hoá đơn) | `qwen2-vl:7b` hoặc `llava` | ~8GB | Phase 2 |

Máy M1 Ultra 64GB+ dư sức chạy song song 9B + embed + vision. Nếu máy yếu (≤16GB): dùng `qwen2.5:3b` hoặc cloud-only.

### LangChain + LangGraph cho agent

- `langchain-core`, `langchain-ollama`, `langchain-deepseek`, `langgraph` — agent loop + tool binding + model abstraction.
- Dùng `langgraph.prebuilt.create_react_agent` (khuyến nghị mới của LangChain team) thay vì `AgentExecutor` cũ.
- Không phải mọi chat turn đều đi qua agent — router quyết định fast path (structured extract) vs agent path. Xem [14-llm-tools.md](./14-llm-tools.md#fast-path-vs-agent-path).

### Langfuse cho observability

- Trace mọi step agent: prompt, tool call, latency, token.
- **Self-host v2** (Postgres-only) trong docker compose profile `obs`, dữ liệu không rời máy.
- **Cloud opt-in** — dữ liệu gửi ra ngoài, cần redact trước, cảnh báo rõ ràng trong UI.
- Complement bằng audit log local SQLite (bảng `llm_tool_call_log`) cho trust-critical.

### Tại sao không dùng MCP (Model Context Protocol)

- MCP là standard tốt cho tool discovery liên server. Dự án này chỉ 1 user, 1 máy, 1 agent → overhead không đáng.
- LangChain `@tool` decorator đủ cho use case này, đơn giản hơn cho dev.
- Khi cần expose tool ra bên ngoài (IDE, Claude Desktop) thì mới cân nhắc MCP phase 3.

### DeepSeek thay vì OpenAI
- Rẻ hơn GPT-4 class ~10 lần.
- API tương thích OpenAI (dễ đổi).
- Tiếng Việt ổn cho tác vụ extract & tóm tắt.

### `uv` thay vì `pip`
- Cài nhanh hơn 10–100 lần.
- Lockfile chuẩn.
- Không cần venv thủ công.

## Cấu trúc repo đề xuất

```
money-tracking/
├── README.md
├── docs/                       # docs bạn đang đọc
├── docker-compose.yml
├── .env.example
├── apps/
│   ├── api/                    # FastAPI
│   │   ├── pyproject.toml
│   │   ├── alembic/
│   │   └── src/money_api/
│   │       ├── main.py
│   │       ├── models/         # SQLAlchemy
│   │       ├── routers/        # endpoints
│   │       ├── services/       # business logic
│   │       ├── llm/
│   │       │   ├── router.py        # fast/agent routing
│   │       │   ├── extract.py       # structured output
│   │       │   ├── agent.py         # LangGraph ReAct
│   │       │   ├── tools/           # @tool functions
│   │       │   ├── policy.py        # allowlist enforcement
│   │       │   ├── tracing.py       # Langfuse handler
│   │       │   └── prompts/
│   │       ├── ingest/         # gmail parser, chat extract
│   │       └── schedulers/
│   ├── bot/                    # Telegram worker
│   │   └── src/money_bot/
│   ├── gmail_poller/           # Gmail polling worker
│   │   └── src/money_gmail/
│   └── web/                    # Next.js
│       ├── package.json
│       └── src/
├── packages/                   # shared (nếu có monorepo)
└── data/                       # volume: SQLite + LLM logs
```

Cả `bot/`, `gmail_poller/`, `api/` đều import chung một package `money_core` (ở `packages/core` hoặc trong `apps/api`) để tránh code lặp.

## Phiên bản tối thiểu

- macOS 13+ / Linux kernel 5.x+ / Windows với WSL2.
- Docker Desktop 4.20+ hoặc Docker Engine 24+.
- 8GB RAM nếu chỉ dùng DeepSeek API.
- 16GB RAM nếu chạy Ollama 7B.
- 20GB disk (model + DB + backup).
