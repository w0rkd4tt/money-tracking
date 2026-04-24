# 05 — Tính năng

Tài liệu mô tả chi tiết từng tính năng và luồng user. Các tính năng kỹ thuật chuyên sâu (LLM, Gmail, Telegram, Dashboard) xem ở file riêng.

## 5.0 Nguồn tiền (Accounts)

### Khái niệm
Mỗi "ví chứa tiền" là một `account`. App hỗ trợ không giới hạn số account, với các loại:

| Type | Ví dụ | Đặc điểm |
|---|---|---|
| `cash` | Tiền mặt VND, USD tiền mặt | Không có email, chỉ nhập tay/chat |
| `bank` | VCB, TCB, MB, TPB, ACB… | Có email thông báo → Gmail ingest |
| `ewallet` | Momo, ZaloPay, ShopeePay, ViettelMoney… | Có email; một số có API (phase 2) |
| `credit` | Thẻ tín dụng (Visa, Master, JCB) | Cần track cả giao dịch và billing cycle |
| `saving` | Sổ tiết kiệm, gửi tiết kiệm online | Ít transaction, chủ yếu balance check |
| `investment` | Chứng khoán, crypto wallet | Phase 2 |

### Quản lý account
- Trang **"Tài khoản"**: list tất cả account, số dư real-time, icon + màu riêng.
- Nút "+ Thêm tài khoản": form với `name, type, currency, opening_balance, icon, color`.
- Archive thay vì xoá (giữ lịch sử).
- Số dư = `opening_balance + SUM(transactions)` (không cache, tính on-the-fly vì DB nhỏ).

### Rút / nạp / chuyển giữa account (Transfer)

Đây là luồng **khác** với chi/thu — phải được tách bạch vì không làm giảm/tăng tổng tài sản.

**UX web:**
- Nút "⇄ Chuyển tiền" ở trang Tài khoản và header.
- Form:
  ```
  Từ:       [VCB      ▼]
  Đến:      [Tiền mặt ▼]
  Số tiền:  [_________ ₫]
  Phí:      [_________ ₫]  (mặc định 0)
  Ngày:     [21/04 14:30]
  Ghi chú:  [Rút ATM]
  ```
- Lưu → sinh 1 `transfer_group` + 2 row `transaction` (âm ở from, dương ở to).

**UX qua chat:**
- User gõ: *"rút 2tr từ VCB về tiền mặt"* hoặc *"chuyển 500k từ tiền mặt sang Momo"*.
- LLM phát hiện `kind=transfer` + `account` + `to_account` → tạo transfer_group.

**UX qua Telegram:**
- `/transfer` wizard từng bước, hoặc chat tự nhiên.
- Button inline `[VCB → Tiền mặt]`, `[Tiền mặt → Momo]` cho lần gần đây.

**Dashboard behavior:**
- Transfer KHÔNG xuất hiện trong "Chi tiêu tháng" hay "Thu nhập tháng".
- Có tab riêng **"Luồng tiền"** xem dòng chảy giữa account (Sankey diagram).
- Khi xem chi tiết 1 account, transfer xuất hiện trong timeline (với icon ⇄ riêng).

### Multi-currency
- Mỗi account có `currency` cố định.
- Transaction lưu theo currency của account.
- Dashboard convert về `DEFAULT_CURRENCY` (VND) dùng `fx_rate` từ ECB hoặc nhập tay.
- MVP: chỉ hỗ trợ VND + USD. Phase 2: nhiều hơn.

### Chính sách account mặc định
- User đặt 1 account làm "default" trong settings → nếu chat/Gmail không rõ account → dùng default thay vì "Chưa xác định".
- Thường default = "Tiền mặt" cho chat web, = account thẻ chính cho Gmail.

## 5.1 Nhập tay qua Web

### Mục đích
Nhập nhanh 1 giao dịch đã xảy ra mà user nhớ. Dùng khi ngồi máy tính và muốn kỷ luật ghi chép.

### UX
- Nút "+ Thêm giao dịch" luôn hiện ở header (phím tắt `n`).
- Modal 1 hàng: `số tiền | account | category | merchant | ngày | ghi chú`.
- Autocomplete merchant từ lịch sử; chọn merchant → auto-suggest category (dùng `merchant.default_category_id`).
- Phím tắt: `Ctrl/Cmd + Enter` = lưu, `Esc` = huỷ.
- Có nút "Mẫu hay dùng" — 5 template gần nhất (ví dụ "Trưa 45k Momo Ăn uống") → nhấn 1 nút xong.

### Backend
- `POST /transactions`, validate, lưu `status = confirmed`, `source = manual`, `confidence = 1.0`.
- Trigger budget check ngay sau insert.

## 5.1a Agentic chat (ReAct + Gmail readonly)

Ngoài việc ghi giao dịch, chat có thể **trả lời câu hỏi** bằng cách tự query DB và đọc Gmail (readonly, có allowlist).

**Ví dụ user gõ:**
- *"Tháng này tôi tiêu ăn uống bao nhiêu?"* → agent query DB → trả lời.
- *"Có email Shopee nào tuần này chưa thanh toán không?"* → agent search Gmail → đọc → trả lời.
- *"Giao dịch VCB gần nhất là gì?"* → agent query DB → trả lời.

**Quy định:**
- Mặc định tắt (`LLM_GMAIL_TOOL_ENABLED=false`). User bật trong Settings.
- Policy allowlist: chỉ những sender/label user duyệt → LLM mới đọc được.
- Mọi tool call ghi audit log + Langfuse trace.
- Agent không tự tạo / sửa / xoá giao dịch — chỉ propose pending để user confirm.

Kỹ thuật: xem [14-llm-tools.md](./14-llm-tools.md).

## 5.2 Chatbot (Web)

### Mục đích
Bỏ form, nhập bằng câu tự nhiên. Thân thiện cho nhập nhiều giao dịch liên tiếp.

### UX
- Sidebar phải / tab "Chat".
- User gõ: *"trưa nay ăn phở 45k bằng momo"*.
- Bot trả về **card preview**:
  ```
  ┌────────────────────────────┐
  │  −45.000 ₫   Momo           │
  │  Ăn uống > Trưa             │
  │  "quán phở" • 21/04 12:30   │
  │  [✓ Đúng]  [Sửa]  [Huỷ]    │
  └────────────────────────────┘
  ```
- Nhấn "Sửa" → form inline sửa từng trường → Save.
- Có thể nhập nhiều dòng một lúc: *"sáng cafe 25k, trưa cơm 50k"* → 2 card.

### Luồng xử lý
1. `POST /chat/message` với `text`.
2. Backend load context: list account, list category (cây rút gọn), top 20 merchant gần đây.
3. Gọi LLM extract (xem [06-llm-strategy.md](./06-llm-strategy.md)) với structured output.
4. Với mỗi giao dịch trích xuất được:
   - Validate số tiền không âm, account tồn tại, category tồn tại (nếu không → nhờ LLM match gần nhất + fallback "Chưa phân loại").
   - Nếu `confidence < 0.8` → tạo `pending` + trả card có highlight trường mơ hồ.
   - Nếu `>= 0.8` → tạo `pending`, chờ confirm explicit (vẫn cần confirm vì LLM có thể hiểu sai).
5. Sau confirm → `status = confirmed`, kích hoạt budget check.

### Ngữ cảnh nhiều lượt
- Giữ `chat_session` 10 tin nhắn gần nhất làm context.
- Cho phép user phản hồi: *"à không, bằng VCB mới đúng"* → LLM tìm transaction vừa tạo, gợi ý edit.

### Transfer qua chat
LLM phân biệt `kind` trong schema:
- *"ăn phở 45k bằng momo"* → `kind=expense`
- *"lương về 25tr"* → `kind=income`
- *"rút 2tr từ VCB về tiền mặt"* → `kind=transfer`, `account="VCB"`, `to_account="Tiền mặt"`, `amount=2000000`
- *"nạp 500k vào Momo từ VCB"* → `kind=transfer`, `account="VCB"`, `to_account="Momo"`

Prompt nêu rõ các keyword hint transfer: `rút, nạp, chuyển, sang, về, từ ... sang ...`.

## 5.3 Chatbot (Telegram)

Cùng core với chat web, chỉ khác adapter. Xem [08-telegram.md](./08-telegram.md).

- Bot poll `getUpdates` mỗi 5s.
- Mỗi message text → gọi cùng service `extract_transaction(text, context)`.
- Card confirm dùng inline keyboard với button `✓ Đúng / ✎ Sửa / ✗ Huỷ / 🏷 Đổi category`.
- Hỗ trợ commands:
  - `/today` — liệt kê giao dịch hôm nay.
  - `/budget` — % budget đã dùng tháng này.
  - `/undo` — xoá giao dịch vừa thêm.
  - `/balance` — số dư từng account.
  - `/help`.

## 5.4 Import từ Gmail

### Mục đích
Đa số ngân hàng VN gửi email thông báo mỗi giao dịch (hoặc SMS-to-email). Đây là nguồn dữ liệu chính xác nhất, không phụ thuộc user ghi chép.

### Yêu cầu
- Google Account có email thông báo ngân hàng/ví.
- OAuth grant scope `gmail.readonly`.

### Luồng
Xem [07-gmail.md](./07-gmail.md). Tóm tắt:
1. Poller chạy 10 phút/lần, incremental sync qua `history.list`.
2. Match rule theo sender/subject → nếu có rule → regex extract.
3. Không rule → gọi LLM (redact số thẻ/STK), sinh rule mới → user confirm → lưu rule.
4. Giao dịch insert `source=gmail`, `status=confirmed` nếu rule đã được user duyệt từ trước, ngược lại `pending`.

### UX phía user
- Trang "Nguồn email" list tất cả email bank đã sync, filter theo status.
- Notification Telegram khi có giao dịch mới từ email (để user verify nhanh).
- Nút "Học email này" khi user tự forward email lạ vào 1 địa chỉ đặc biệt (phase 2).

## 5.5 Budget & cảnh báo

### Mục đích
Tự động theo dõi chi tiêu so với ngân sách, cảnh báo khi vượt.

### Setup
- Trang "Ngân sách": cho mỗi category leaf, đặt limit/tháng hoặc /tuần.
- Tuỳ chọn rollover: tháng này dư 200k → tháng sau budget = limit + 200k.

### Cảnh báo
Trigger sau mỗi transaction `confirmed`:
- 50%, 80%, 100%, 120% → push notify Telegram (chỉ 1 lần/ngưỡng/kỳ).
- Tin nhắn mẫu:
  ```
  ⚠️ Ăn uống: 2.4M / 3M (80%) tháng 4
  Còn 600k trong 9 ngày (66k/ngày).
  ```

### Bất thường (anomaly)
- Giao dịch > P95 amount của category → Telegram hỏi "giao dịch này lớn hơn bình thường, đúng không?".
- Merchant chưa từng thấy + amount > 200k → hỏi xác nhận.

## 5.5b Kế hoạch tháng & phân bổ dòng tiền

### Mục đích
Kiểm soát dòng tiền trước khi tiêu: thu nhập → chia vào **bucket (nhóm mục đích)** → category tự chảy vào bucket → theo dõi quota còn lại.

### Khái niệm
- **Allocation bucket**: nhóm mục đích, tái sử dụng qua các tháng (ví dụ "Thiết yếu", "Mong muốn", "Tiết kiệm", "Đầu tư"). Mỗi bucket gom nhiều category (1 category = 1 bucket để tránh double-count, chỉ kind=expense được map).
- **Monthly plan**: 1 bản ghi/tháng (`month`, `expected_income`, `strategy`, `carry_over_enabled`, `note`).
- **Plan allocation**: mỗi bucket trong 1 plan có `method` (amount|percent), `value`, `rollover`.

### 4 chiến lược vận hành (`plan.strategy`)
1. **soft** — chỉ cảnh báo khi vượt, không chặn.
2. **envelope** — bucket hết quota → từ chối quick-add ở Telegram, buộc xác nhận.
3. **zero_based** — tổng allocation phải = expected_income (ép user gán hết tiền).
4. **pay_yourself_first** — bucket "Tiết kiệm" trừ trước ngay đầu tháng.

### Dòng tiền trong 1 tháng
- Ngày 1: mở plan (hoặc copy từ tháng trước qua `POST /plans/{target}/copy-from/{src}`). Expected income có thể auto-suggest từ trung bình 3 tháng gần nhất (`GET /plans/suggest-income`).
- Trong tháng: tx `kind=expense` có category thuộc bucket → spent bucket tăng. Tx `kind=income` → cộng vào `actual_income`.
- Cuối tháng: nếu `rollover=true` trên allocation + `carry_over_enabled=true` trên plan → dư/vượt của bucket tháng này (signed) được cộng vào `carry_in` của cùng bucket tháng sau.

### Ngưỡng cảnh báo (theo bucket, dùng lại pipeline notify)
- 80% (`status=warn`), 100% (`status=over`) — gửi Telegram qua `notify_log` (dedup theo `event_key`).

### API
| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/buckets` | list bucket |
| `POST` | `/buckets` | tạo bucket + gán category |
| `PATCH` | `/buckets/{id}` | rename/replace category mapping |
| `DELETE` | `/buckets/{id}` | xoá (RESTRICT nếu đang có allocation dùng) |
| `GET` | `/plans` | list plan các tháng |
| `POST` | `/plans` | tạo plan + allocations |
| `GET` | `/plans/{YYYY-MM}` | chi tiết plan |
| `PATCH` | `/plans/{YYYY-MM}` | sửa, tuỳ chọn replace allocations |
| `DELETE` | `/plans/{YYYY-MM}` | xoá |
| `GET` | `/plans/{YYYY-MM}/summary` | tính realtime từng bucket (allocated/spent/carry_in/remaining/pct/status) |
| `POST` | `/plans/{target}/copy-from/{src}` | clone plan tháng trước |
| `GET` | `/plans/suggest-income?month=YYYY-MM` | gợi ý expected_income từ avg 3 tháng trước |

### Bảng mới (migration 0004)
`allocation_bucket`, `bucket_category` (M2M), `monthly_plan` (unique `month`), `plan_allocation` (unique `(monthly_plan_id, bucket_id)`).

### Quan hệ với Budget (5.5)
- 2 tầng độc lập: **Bucket** = chiến lược phân bổ thu nhập; **Budget** = giới hạn chi tiết từng category trong bucket.
- User có thể dùng 1 hoặc cả 2 tuỳ độ kỷ luật.

## 5.6 Dashboard

### Trang chính
- Thẻ tổng: số dư tổng, chi tháng, thu tháng, chênh lệch so với tháng trước.
- Biểu đồ pie chi theo category (tháng hiện tại).
- Biểu đồ line 6 tháng gần nhất, tách thu/chi.
- Top 5 merchant chi tiêu nhiều nhất tháng.
- Danh sách giao dịch mới nhất (phân trang).

### Trang chi tiết category
- Bar chart tháng hiện tại theo ngày.
- So sánh avg 3 tháng gần nhất.
- Danh sách giao dịch trong category.

### Filter & search
- Time range, account, category, merchant, tag, text trong note.
- Export CSV cho range đã chọn.

## 5.7 Insight định kỳ

### Weekly digest (Chủ nhật 20:00)
Scheduler gọi LLM sinh báo cáo ngắn, push Telegram:
```
📊 Tuần 21-27/04
Chi: 1.8M (↓15% so với tuần trước)
Cao nhất: Ăn uống 780k (4 lần)
Bất thường: Grab 320k thứ 5 (lớn gấp 3 bình thường)
💡 Gợi ý: giảm ăn ngoài 2 bữa/tuần có thể tiết kiệm ~400k/tháng.
```

### Monthly summary (ngày 1 tháng sau)
- Tổng kết thu/chi.
- Vượt/đạt/dưới budget từng category.
- So sánh 3 tháng.
- Gửi cả Telegram và email tự gửi cho user.

## 5.8 Quản lý rule & merchant

- Trang "Học máy" list các rule đã có (nguồn: user thủ công / LLM suggest).
- Mỗi rule: có thể bật/tắt, xem số lần match, xoá.
- Merchant canonical: user có thể merge alias vào 1 merchant, set default category.

## 5.9 Backup & restore

- Auto dump SQLite hàng đêm vào `data/backups/`.
- Retention 30 ngày.
- UI có nút "Tải backup" → file `.db`.
- Restore: CLI `make restore FILE=...` (không làm UI để tránh nhầm).

## Ưu tiên MVP

| Feature | MVP | Sau MVP |
|---|---|---|
| 5.1 Nhập tay | ✅ | — |
| 5.1a Agentic chat (ReAct + Gmail tool) | — | ✅ phase 2 |
| 5.2 Chat web | ✅ | cải thiện multi-turn |
| 5.3 Chat Telegram | ✅ | voice message |
| 5.4 Gmail (2 bank) | ✅ | forward email, nhiều bank |
| 5.5 Budget + notify | ✅ cơ bản | anomaly detection |
| 5.5b Kế hoạch tháng + bucket | ✅ backend (M0004) | UI + Sankey + Telegram nudge |
| 5.6 Dashboard | ✅ cơ bản | drill-down |
| 5.7 Insight | — | weekly + monthly |
| 5.8 Rule mgmt | ✅ cơ bản (list + tắt) | drag-drop, test rule |
| 5.9 Backup | ✅ auto | UI restore |
