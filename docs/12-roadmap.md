# 12 — Roadmap

## Milestone & thứ tự thực thi

Ưu tiên cắt dọc (vertical slice): mỗi milestone giao được 1 tính năng dùng được end-to-end, không làm ngang toàn bộ layer.

### M0 — Scaffold (0.5 tuần)
- [ ] Repo, monorepo layout, `.env.example`.
- [ ] Docker compose: api + web + ollama + volume.
- [ ] FastAPI "hello world" + health check.
- [ ] Next.js skeleton + Tailwind + shadcn.
- [ ] Alembic init, migration rỗng chạy được.
- [ ] CI: lint + type check (ruff, mypy, tsc, eslint).

**Exit**: `docker compose up` start được 3 service, web mở ra trang trắng có link "health ok".

---

### M1 — Nhập tay, multi-account & dashboard cơ bản (1 tuần)
- [ ] Migration: `account`, `category`, `merchant`, `transaction`, `tag`, `transfer_group`.
- [ ] Seed category mặc định (Ăn uống, Đi lại, Hoá đơn, Lương, Transfer…).
- [ ] CRUD `/accounts`, `/categories`, `/transactions`.
- [ ] Endpoint transfer: `POST /transfers` sinh 1 group + 2 transaction.
- [ ] Web: settings tạo account (nhiều bank, tiền mặt, ewallet).
- [ ] Web: form nhập tay + form transfer (⇄).
- [ ] Web: dashboard MVP — KPI cards, pie chi category, line cashflow, accounts panel. Xem [13-dashboard.md](./13-dashboard.md).
- [ ] Util format VND, timezone VN.

**Exit**: nhập 20 giao dịch + 3 transfer (rút ATM, nạp Momo, chuyển bank), dashboard hiện tổng đúng (transfer không đếm vào chi/thu), mỗi account có số dư chính xác.

---

### M2 — LLM chat extract (web) (1 tuần)
- [ ] Setup `m1ultra` provider: Ollama native host + pull `jaahas/qwen3.5-uncensored:9b`.
- [ ] `LLM Router` module với provider interface, structured output JSON schema.
- [ ] `POST /chat/message` pipeline: context → extract → validate.
- [ ] Hỗ trợ `kind=transfer` trong schema (rút/nạp/chuyển).
- [ ] Web: chat UI (sidebar), card confirm, inline edit.
- [ ] Golden test 20 case Việt/Anh bao gồm transfer.
- [ ] Log LLM vào `logs/llm.jsonl`.

**Exit**: "trưa nay ăn phở 45k bằng momo" → card → confirm → DB đúng. "rút 2tr từ VCB về tiền mặt" → transfer_group + 2 transaction đúng.

---

### M3 — Telegram bot (1 tuần)
- [ ] `apps/bot` worker với loop short polling 5s.
- [ ] Persist offset vào `sync_state`.
- [ ] Whitelist chat_id.
- [ ] Commands: `/start`, `/today`, `/balance`, `/last`, `/undo`, `/help`.
- [ ] Forward text message qua API `/chat/message`.
- [ ] Inline keyboard confirm/reject/edit.
- [ ] Notify outgoing từ API (module `notifier`).

**Exit**: chat từ Telegram giống hệt web, confirm bằng button.

---

### M4 — Gmail ingest (1.5 tuần)
- [ ] OAuth flow + store refresh_token (encrypted).
- [ ] `apps/gmail_poller` worker mỗi 10 phút.
- [ ] Bootstrap baseline `historyId`.
- [ ] Rule engine linh hoạt: user chọn 2 sender ưu tiên đầu (xem email thực tế của user). Template rule sẵn cho VCB, TCB, MB, TPB, Momo, ZaloPay, Shopee — user enable cái nào cần.
- [ ] Phát hiện transfer từ email (rút ATM, nạp ví) → tạo `transfer_group` thay vì 1 giao dịch lẻ.
- [ ] Ingest endpoint + dedupe.
- [ ] LLM fallback (`m1ultra`) với redaction.
- [ ] UI "Nguồn email" list, rule management, UI enable template theo bank.
- [ ] Notify Telegram khi có email mới cần confirm.

**Exit**: Email bank ưu tiên của user → 10 phút sau có trong DB + Telegram ping. Rút ATM hiện thành transfer đúng, không thành "chi 2tr".

---

### M4.5 — Agent ReAct + Gmail readonly tool + Langfuse (1 tuần)
- [ ] Setup LangChain + LangGraph + Langfuse SDK.
- [ ] Langfuse self-host profile `obs` trong docker-compose.
- [ ] `llm.agent` module: `create_react_agent` với m1ultra (agent model).
- [ ] Router fast/agent path (heuristic ban đầu).
- [ ] Tools: `gmail.search`, `gmail.read_message`, `db.query_transactions`, `db.balance`, `propose_transaction`.
- [ ] Policy engine: bảng `llm_gmail_policy`, query rewrite, deny-by-default.
- [ ] Audit log: bảng `llm_tool_call_log`, retention 90 ngày.
- [ ] Cache search results cho enforcement `read_message`.
- [ ] UI Settings "Quyền LLM truy cập Gmail": allowlist/denylist, test pattern, xem audit.
- [ ] Rate limit + prompt injection mitigation (delimiter tool observation).

**Exit**: Thêm allow `*@shopee.vn`, user hỏi "tháng này tôi có đơn Shopee nào chưa pay?" → agent search + read + trả lời đúng. Thử prompt injection trong email → agent không làm theo. Tất cả trace hiện trong Langfuse UI.

### M5 — Budget & cảnh báo (0.5 tuần)
- [ ] Migration `budget`.
- [ ] UI set budget theo category/tháng.
- [ ] Trigger sau mỗi transaction: check threshold.
- [ ] `notifier.budget_threshold`: 50/80/100/120%.
- [ ] Dedup notify (1 lần / ngưỡng / kỳ).
- [ ] `/budget` command Telegram.

**Exit**: Set budget Ăn uống 3M → tiêu tới 2.4M → Telegram 80%.

---

### M6 — Insight định kỳ (0.5 tuần)
- [ ] APScheduler job: weekly digest (CN 20:00), monthly (ngày 1).
- [ ] Prompt digest, input là stats đã compute.
- [ ] `/reports/weekly`, `/reports/monthly`.
- [ ] Telegram gửi báo cáo.

**Exit**: Chủ nhật 20:00 nhận tin nhắn Telegram 120 từ tổng kết tuần.

---

### M7 — Polish & release MVP (0.5 tuần)
- [ ] Export CSV.
- [ ] Backup scheduler + prune.
- [ ] UI settings toàn bộ: tài khoản, category, budget, LLM cloud toggle.
- [ ] README + setup guide đầy đủ.
- [ ] Golden test pass rate ≥ 90%.
- [ ] Manual QA checklist hoàn thành.

**Exit**: user mới clone → setup theo README → chạy được MVP trong < 30 phút.

---

## Post-MVP (sau M7)

### Phase 2 — Nice to have
- Voice message Telegram (Whisper).
- OCR hoá đơn (VLM qwen2-vl).
- Drill-down dashboard theo category.
- Rule playground UI test regex.
- Anomaly detection nâng cao (Z-score, IQR).
- Forward email tự học rule mới.

### Phase 3 — Mở rộng
- Multi-user (gia đình share budget).
- Mobile PWA.
- SMS banking qua Android app forward.
- Đầu tư / portfolio tracking cơ bản.
- Webhook mode cho Telegram (tùy chọn).
- Postgres backend cho multi-user.

### Phase 4 — Polish sâu
- Biểu đồ so sánh năm, YTD.
- Forecast chi tiêu dựa trên xu hướng.
- Gợi ý tối ưu chi tiêu (LLM agent).
- Export sổ cái theo chuẩn kế toán.

---

## Cột mốc thời gian (ước tính)

| Tuần | Milestone |
|---|---|
| 1 | M0 + M1 |
| 2 | M2 |
| 3 | M3 |
| 4 | M4 (tuần 1/2) |
| 5 | M4 (tuần 2/2) + M5 |
| 6 | M6 + M7 |
| 7 | M4.5 (Agent + Gmail tool + Langfuse) |

Tổng: **6 tuần part-time** có MVP core, **thêm 1 tuần** cho agent layer (M4.5 có thể làm song song nếu có thời gian).

## Risk tracking

| Risk | Xác suất | Impact | Mitigation |
|---|---|---|---|
| LLM 7B hallucination cao tiếng Việt | Trung bình | Cao | Golden test + fallback cloud + user confirm bắt buộc |
| Máy user RAM < 16GB | Cao | Trung bình | Hỗ trợ cloud-only mode, 3B model alt |
| Gmail OAuth verification | Thấp | Cao | Dùng test user mode (1 user OK không cần verify) |
| Ngân hàng đổi format email | Trung bình | Trung bình | LLM fallback tự học rule mới |
| Telegram limit bot | Thấp | Thấp | Không vấn đề với 1 user |
| User mất device | Thấp | Cao | Backup mã hoá + khuyến nghị disk encryption |

## Quyết định đã chốt

- [x] **LLM provider**: `m1ultra` (Ollama native trên M1 Ultra) với `jaahas/qwen3.5-uncensored:9b`, timeout 120s. Xem [03-tech-stack.md](./03-tech-stack.md#provider-m1ultra--ollama-chạy-native-trên-host).
- [x] **Ngân hàng/ví**: thiết kế **multi-account linh hoạt**, không hard-code cụ thể — user thêm account tuỳ ý (nhiều bank + tiền mặt + ewallet), có luồng rút/nạp giữa account. Parser Gmail ưu tiên 2 nguồn đầu tiên theo user chỉ định (cấu hình sau). Xem [05-features.md § 5.0](./05-features.md#50-nguồn-tiền-accounts).
- [x] **Deployment**: Docker Compose (trừ Ollama chạy native host để tận dụng Metal GPU). Xem [11-deployment.md](./11-deployment.md).
- [x] **Single-user** cho MVP; schema không cần `user_id` nhưng để slot mở rộng sau.
- [x] **Telegram**: short polling 5s.

## Quyết định open (còn lại)

- [ ] Khi nào enable DeepSeek cloud fallback (user tự bật khi cần).
- [ ] Parser Gmail ưu tiên ngân hàng cụ thể nào trong số banks user dùng (sẽ chọn ở giai đoạn M4, dựa trên email thực tế của user).

Cập nhật file này khi có quyết định mới.
