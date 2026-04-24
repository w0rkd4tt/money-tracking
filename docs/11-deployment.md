# 11 — Triển khai

## Yêu cầu máy

| Thành phần | Tối thiểu | Khuyến nghị |
|---|---|---|
| OS | macOS 13+ / Linux / Windows WSL2 | macOS 14+ hoặc Ubuntu 22.04+ |
| CPU | 4 core | 8 core |
| RAM | 8 GB (cloud LLM mode) | 16 GB (Ollama 7B) |
| Disk | 20 GB | 50 GB (có Ollama + backup) |
| GPU | không bắt buộc | NVIDIA với 8GB VRAM giúp Ollama nhanh gấp 5 lần |

## Cài tiên quyết

- Docker Desktop 4.20+ (macOS/Windows) hoặc Docker Engine 24+ (Linux).
- `ollama` cài native nếu muốn (hoặc dùng container — xem dưới).

## `.env.example`

Xem file [`.env.example`](../.env.example) ở root repo. Điểm đáng chú ý:

- **Provider LLM là `m1ultra`** (Ollama native trên host), không bọc Docker để tận dụng Metal GPU macOS.
- Từ trong container → host: dùng `http://host.docker.internal:11434`.
- Chạy native (không Docker): dùng `http://127.0.0.1:11434`.
- `LLM_ALLOW_CLOUD=false` mặc định; cloud fallback (DeepSeek) là opt-in.

## `docker-compose.yml`

Ollama **không** nằm trong compose — chạy native trên host macOS để tận dụng Metal GPU. Các service trong compose kết nối ra host qua `host.docker.internal`.

```yaml
name: money-tracking

x-common: &common
  env_file: .env
  restart: unless-stopped
  # Cho phép container nói chuyện với host (Ollama native).
  # Trên Docker Desktop (macOS/Windows), host.docker.internal đã sẵn.
  # Trên Linux: thêm dòng extra_hosts dưới đây (bỏ comment).
  # extra_hosts:
  #   - "host.docker.internal:host-gateway"

services:
  api:
    <<: *common
    build: ./apps/api
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "${APP_BIND:-127.0.0.1}:${APP_PORT_API:-8000}:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 3s
      retries: 3

  web:
    <<: *common
    build: ./apps/web
    depends_on: [api]
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:${APP_PORT_API:-8000}/api/v1
    ports:
      - "${APP_BIND:-127.0.0.1}:${APP_PORT_WEB:-3000}:3000"

  bot:
    <<: *common
    build: ./apps/bot
    depends_on: [api]
    environment:
      API_URL: http://api:8000/api/v1
    volumes:
      - ./data:/app/data
    deploy:
      replicas: 1   # BẮT BUỘC 1 để không trùng offset Telegram

  gmail:
    <<: *common
    build: ./apps/gmail_poller
    depends_on: [api]
    environment:
      API_URL: http://api:8000/api/v1
```

### Profile `obs` — Langfuse self-host (optional)

File riêng `docker-compose.obs.yml`:

```yaml
# Bật: docker compose -f docker-compose.yml -f docker-compose.obs.yml up -d
# Hoặc dùng profiles:
#   docker compose --profile obs up -d

services:
  langfuse-db:
    image: postgres:16-alpine
    profiles: ["obs"]
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: ${LANGFUSE_DB_PASSWORD}
    volumes: [langfuse-pg:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 10s

  langfuse:
    image: langfuse/langfuse:2
    profiles: ["obs"]
    depends_on:
      langfuse-db: {condition: service_healthy}
    environment:
      DATABASE_URL: postgresql://langfuse:${LANGFUSE_DB_PASSWORD}@langfuse-db:5432/langfuse
      NEXTAUTH_URL: http://localhost:3001
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET}
      SALT: ${LANGFUSE_SALT}
      TELEMETRY_ENABLED: "false"
      LANGFUSE_INIT_ORG_ID: money-tracking
      LANGFUSE_INIT_PROJECT_ID: money-tracking
    ports:
      - "127.0.0.1:3001:3000"

volumes:
  langfuse-pg:
```

Chạy lần đầu:
```bash
# Sinh secrets
echo "LANGFUSE_DB_PASSWORD=$(openssl rand -base64 24)" >> .env
echo "LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -base64 32)" >> .env
echo "LANGFUSE_SALT=$(openssl rand -base64 32)" >> .env

docker compose --profile obs up -d langfuse-db langfuse
open http://localhost:3001   # tạo account owner, lấy Public/Secret key
# Paste vào LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY trong .env
docker compose restart api
```

Không muốn observability → để `LANGFUSE_ENABLED=false`, bỏ profile `obs`.

## Ollama trên host (ngoài Docker)

```bash
# Cài Ollama native macOS
brew install ollama
# hoặc tải https://ollama.com/download

# Chạy server (sẽ listen 127.0.0.1:11434)
ollama serve &

# Pull model
ollama pull jaahas/qwen3.5-uncensored:9b
ollama pull nomic-embed-text

# Kiểm tra
curl http://127.0.0.1:11434/api/tags
```

Trong `.env`:
```
M1ULTRA_URL=http://host.docker.internal:11434   # khi dùng Docker
# M1ULTRA_URL=http://127.0.0.1:11434           # khi native dev
```

## Thứ tự start

1. Ollama native trên host (sẵn sàng trước khi `docker compose up`).
2. `api` migration DB + serve.
3. `bot`, `gmail`, `web` phụ thuộc api.

## Lần đầu setup

```bash
# 1. Clone & cấu hình
git clone <repo> && cd money-tracking
cp .env.example .env

# 2. Sinh encryption key + session secret
echo "APP_ENCRYPTION_KEY=$(openssl rand -base64 32)" >> .env.local
echo "SESSION_SECRET=$(openssl rand -base64 32)" >> .env.local
# → merge giá trị vào .env (hoặc sửa tay)

# 3. Cài & chạy Ollama native trên host
brew install ollama
ollama serve &
ollama pull jaahas/qwen3.5-uncensored:9b
ollama pull nomic-embed-text

# 4. Chuẩn bị data dir
mkdir -p data/backups logs
chmod 700 data

# 5. Điền vào .env:
#    - TELEGRAM_BOT_TOKEN (BotFather)
#    - GOOGLE_CLIENT_ID/SECRET (Google Cloud Console, OAuth Desktop)
#    - M1ULTRA_URL=http://host.docker.internal:11434

# 6. Start services (KHÔNG có Ollama vì nó chạy native)
docker compose up -d

# 7. Migrate DB (lần đầu)
docker compose exec api alembic upgrade head

# 8. Theo dõi log
docker compose logs -f api bot gmail

# 9. Mở web → tạo accounts + categories đầu tiên
open http://localhost:3000

# 10. Kết nối Gmail (trong Settings UI)

# 11. Setup Telegram bot
#  - Chat với bot, gửi /start
#  - Lấy chat_id từ log bot, thêm vào TELEGRAM_ALLOWED_CHAT_IDS trong .env
#  - docker compose restart bot
```

## Cập nhật

```bash
git pull
docker compose build --pull
docker compose up -d
docker compose exec api alembic upgrade head
```

## Backup

### Auto (scheduler trong api)
```
Daily 02:00:
  sqlite3 /app/data/money.db ".backup /app/data/backups/money-$(date +%F).db"
  age -r $BACKUP_PUBKEY ... (nếu có)
  prune files > 30 ngày
```

### Manual
```bash
docker compose exec api python -m money_api.cli backup now
```

### Restore
```bash
docker compose down
cp data/backups/money-2026-04-20.db data/money.db
docker compose up -d
```

## Monitoring

### Log
- Container log: `docker compose logs -f <service>`.
- App log file: `logs/<service>.jsonl`.
- LLM interaction log: `logs/llm.jsonl`.

### Metrics (tuỳ chọn)
- Expose `/metrics` Prometheus ở api.
- Run Grafana + Prometheus container nếu muốn dashboard (phase 2).

### Health check
- `curl http://localhost:8000/api/v1/health` → `{"status":"ok","db":"ok","ollama":"ok"}`.
- Telegram: nếu bot offline 5 phút → scheduler notify qua email (phase 2).

## Chạy dev không Docker

```bash
# Terminal 1 — Ollama
ollama serve
ollama pull jaahas/qwen3.5-uncensored:9b

# Terminal 2 — API
cd apps/api
uv sync
uv run alembic upgrade head
uv run uvicorn money_api.main:app --reload --port 8000

# Terminal 3 — Web
cd apps/web
pnpm install
pnpm dev

# Terminal 4 — Bot
cd apps/bot
uv sync
uv run python -m money_bot

# Terminal 5 — Gmail poller
cd apps/gmail_poller
uv sync
uv run python -m money_gmail
```

## Troubleshoot nhanh

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| Container không gọi được Ollama | `M1ULTRA_URL=127.0.0.1` trong Docker | Đổi sang `http://host.docker.internal:11434` |
| `host.docker.internal` unknown (Linux) | Docker Engine không có alias này | Thêm `extra_hosts: ["host.docker.internal:host-gateway"]` vào compose |
| Ollama không response | Server chưa chạy | `ollama serve`, `ps aux \| grep ollama` |
| Model chưa pull | Chưa `ollama pull` | `ollama pull jaahas/qwen3.5-uncensored:9b` |
| LLM trả JSON rác | Model không hỗ trợ JSON mode tốt | Giảm temperature=0, fallback model khác |
| Inference chậm (>30s) | CPU fallback (container) | Đảm bảo Ollama chạy native host, không trong Docker |
| Bot không nhận tin | Whitelist sai chat_id | Check `docker compose logs bot`, copy chat_id |
| Bot nhận tin lặp | Offset không persist | Check volume `data/` mount, restart bot |
| Gmail `historyId invalid` | Offline > 7 ngày | Poller tự bootstrap, chờ 1 chu kỳ |
| Web UI không gọi được API | CORS / URL env sai | Check `NEXT_PUBLIC_API_URL` trùng bind api |

## Production (sau MVP)

Nếu user muốn chạy 24/7 trên home server:

- Systemd service wrap docker compose.
- Reverse proxy Caddy + Tailscale cho HTTPS + ACL.
- UPS / cron health-check.
- Backup offsite (rsync sang NAS hoặc Proton Drive).
