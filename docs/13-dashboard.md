# 13 — Dashboard tracking

Dashboard là mặt tiền của app — nơi user thấy **ngay** tình hình tài chính trong < 2 giây. Các phần đa số chi tiêu thời gian đọc là Section 1–5 (MVP), còn lại là phase sau.

## Nguyên tắc thiết kế

1. **Density cao mà không rối**: nhiều số trên 1 màn hình nhưng có hierarchy rõ (size, màu, whitespace).
2. **Filter theo kỳ là toàn cục**: đổi range → mọi widget cập nhật cùng lúc.
3. **Drill-down 1 click**: click pie slice → list transaction của slice đó.
4. **Không chart vô nghĩa**: mỗi biểu đồ phải trả lời 1 câu hỏi cụ thể.
5. **Transfer KHÔNG đếm vào chi/thu** (xem [04-data-model.md](./04-data-model.md#transfer_group)).

## Layout tổng thể

```
┌─────────────────────────────────────────────────────────────────────┐
│ Header: [logo] [Range: Tháng 4/2026 ▼] [Account: Tất cả ▼]  [⇄] [+] │
├─────────────────────────────────────────────────────────────────────┤
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                        │
│  │ Tổng   │ │ Chi    │ │ Thu    │ │ Net    │   ← Row 1: KPI cards  │
│  │ tài sản│ │ tháng  │ │ tháng  │ │ saving │                        │
│  └────────┘ └────────┘ └────────┘ └────────┘                        │
├──────────────────────────────────┬──────────────────────────────────┤
│                                  │                                  │
│  Cash flow (line, 90 ngày)        │  Breakdown (pie, chi category)   │
│                                  │                                  │
├──────────────────────────────────┼──────────────────────────────────┤
│  Budget progress (bar list)      │  Top merchants (list)            │
├──────────────────────────────────┴──────────────────────────────────┤
│  Accounts panel: số dư + biến động từng account                     │
├─────────────────────────────────────────────────────────────────────┤
│  Recent transactions (feed, filter + search)                        │
└─────────────────────────────────────────────────────────────────────┘
```

## Time controls (toàn cục)

Dropdown hoặc chip selector:
- `Hôm nay` / `Tuần này` / `Tháng này` (default) / `Quý này` / `Năm này`
- `Tháng trước` / `3 tháng gần nhất` / `6 tháng` / `12 tháng` / `YTD`
- `Custom` → date range picker

Tuỳ chọn so sánh: `Compare with previous period` — toggle → mọi widget thêm chỉ số `↑15%` hoặc `↓8%`.

Account filter:
- `Tất cả` (default) / từng account / multi-select.
- Khi chọn 1 account, widget chuyển sang view account-centric (xem Section 6).

## Section 1 — KPI cards

| Card | Công thức | Phụ |
|---|---|---|
| **Tổng tài sản** | `Σ account.balance` (convert về VND) | Tách cash vs bank ở tooltip |
| **Chi tháng** | `Σ ABS(amount) WHERE kind=expense AND status=confirmed` | So với avg 3 tháng gần |
| **Thu tháng** | `Σ amount WHERE kind=income` | So với cùng kỳ năm trước |
| **Tiết kiệm net** | `thu - chi` | Tỷ lệ % thu (nếu > 0) |

Mỗi card hiện thêm:
- Giá trị chính (size lớn).
- Δ so kỳ trước (màu xanh/đỏ).
- Mini sparkline 30 ngày.

Click vào card → navigate đến view chi tiết.

## Section 2 — Cashflow chart

Line chart kép trên 1 trục:
- Trục X: ngày trong kỳ.
- Line 1 (đỏ, nét đứt): chi luỹ kế.
- Line 2 (xanh, liền): thu luỹ kế.
- Area fill giữa 2 line → thể hiện net saving tăng/giảm.
- Đường tham chiếu: budget limit tháng (ngang, đứt).

Hover → tooltip hiện: `Ngày X: chi A, thu B, net C, còn lại budget D ngày Y`.

Toggle "Daily" vs "Cumulative".

## Section 3 — Breakdown theo category (pie + bar)

### Pie chart — top-level category
- 7 category chi lớn nhất + "Khác" gộp phần còn lại.
- Hover → %, amount tuyệt đối, số transaction.
- Click slice → drill-down vào subcategory (pie cấp 2).
- Click lần 2 → list transaction.

### Bar chart — so sánh tháng
- X: 6 tháng gần nhất.
- Stacked bar theo category → thấy xu hướng.
- Toggle "Normalized" (100% stacked) → thấy tỷ trọng.

## Section 4 — Budget progress

List từng budget đang active:

```
Ăn uống        ████████▓░░  80%  2.400.000 / 3.000.000       ⚠️
Đi lại         ████░░░░░░░  40%    600.000 / 1.500.000
Giải trí       ██████████▓ 105%    525.000 /   500.000       🔴
Hoá đơn        ████████░░░  72%  1.080.000 / 1.500.000
                                                              
+ Thêm budget
```

- Thanh progress màu: xanh < 80%, vàng 80–99%, đỏ ≥ 100%.
- Hiện "còn X ngày" và "còn Y ₫" kế bên.
- Click → list transaction của category trong kỳ.
- Button "Điều chỉnh" mở modal sửa limit.

## Section 5 — Top merchants & tags

2 list nhỏ cạnh nhau:

**Top 5 merchant chi nhiều nhất (tháng)**
```
1. Grab           850.000   (18 lần)
2. Highland       640.000   (22 lần)
3. VinMart        520.000   ( 8 lần)
4. Shopee         480.000   ( 5 lần)
5. Tiki           290.000   ( 3 lần)
```

**Tag sum (tháng)**
```
#cong-tac    2.100.000
#qua-tang      780.000
#gia-dinh      550.000
```

Click 1 row → filter transaction theo merchant/tag.

## Section 6 — Accounts panel

Grid các card account:

```
┌─────────────────────┐ ┌─────────────────────┐
│ 🏦 VCB              │ │ 💵 Tiền mặt         │
│  15.234.000 ₫       │ │     820.000 ₫       │
│  ↓ 2.3M trong tuần  │ │  ↑ 2.0M trong tuần  │
│  [21 giao dịch]     │ │  [8 giao dịch]      │
└─────────────────────┘ └─────────────────────┘
```

Click card → view chi tiết account:
- Timeline giao dịch account.
- Balance history chart (line).
- Inflow / outflow split (stacked bar daily).
- Luồng chuyển đi/đến từ account khác (xem Section 7).

## Section 7 — Luồng tiền giữa account (Sankey)

Tab riêng trong dashboard hoặc mở từ Accounts panel.

```
Lương ─────┬─→ VCB ───┬─→ Tiền mặt ──→ Chi tiêu
           │          └─→ Momo ──→ Chi tiêu online
           └─→ TCB (saving)
```

- Nguồn bên trái: Income sources.
- Giữa: Accounts.
- Phải: Expense categories tổng.
- Độ dày dòng = giá trị.
- Lọc theo kỳ.

Giúp user thấy tiền "chảy" ra sao, đặc biệt khi rút/nạp nhiều giữa bank và tiền mặt.

## Section 8 — Recent transactions feed

Table / list responsive:

| Ngày | Account | Merchant | Category | Số tiền | Nguồn |
|---|---|---|---|---|---|
| 21/04 12:30 | Momo | quán phở | Ăn uống > Trưa | −45.000 | 💬 chat |
| 21/04 09:15 | VCB | Shopee | Mua sắm > Online | −280.000 | 📧 gmail |
| 20/04 20:00 | VCB → Tiền mặt | — | ⇄ Transfer | 2.000.000 | ✋ manual |

- Icon nguồn: ✋ manual / 💬 chat / 📧 gmail / 🤖 bot.
- Hàng pending (chưa confirm): bg vàng nhạt + button confirm inline.
- Transfer hiển thị cả 2 chân hoặc gộp 1 dòng (toggle).
- Phân trang, infinite scroll.
- Search: text trong note/merchant, operator `amount:>100000`, `account:VCB`.
- Action menu: Sửa / Xoá / Đổi category / Merge duplicate.

Bulk action: chọn nhiều row → "Gắn tag", "Đổi category", "Xoá".

## Section 9 — Filters & drill-down global

Thanh filter sidebar (thu gọn mặc định):
- Account (multi).
- Category (cây).
- Tag (multi).
- Status (confirmed / pending / rejected).
- Source (manual / chat / gmail / bot).
- Amount range.
- Text search.

Lưu bộ filter thành "View" (vd: "Chi cho gia đình", "Công tác Q2") — quick-switch.

## Section 10 — Insight box (LLM-generated)

Card nhỏ cuối dashboard, hiện 1–2 insight ngắn do LLM sinh:

```
💡 Tuần này bạn chi ăn uống nhiều hơn 30% so với tuần trước, chủ yếu ở
   "Highland" (6 lần). Nếu duy trì, cuối tháng sẽ vượt budget Ăn uống.
```

- Regenerate mỗi khi user mở dashboard (cache 1h).
- Button "Bỏ qua" → không hiện insight này nữa trong kỳ.
- Button "Hành động" → shortcut (vd: "Đặt giới hạn Highland 200k/tháng" tạo rule).

## Section 11 — Goal tracker (phase 2)

Mục tiêu tiết kiệm dài hạn:
```
🎯 Mua MacBook M5 — 45.000.000
   ████████░░░  62%   Còn 17M  (ETA 3 tháng với tốc độ hiện tại)
```

Dựa trên net saving trung bình 3 tháng gần nhất.

## Section 12 — Compare mode (phase 2)

Toggle "Compare" → chia dashboard 2 cột, chọn 2 khoảng so sánh:
- Tháng này vs tháng trước.
- Năm này vs năm trước.
- Tuần chẵn vs tuần lẻ.
- Trước/sau 1 mốc (vd: trước/sau lương tháng 13).

Mỗi widget hiện song song 2 giá trị + % delta.

## Performance

### Backend
- View data được cache 60s trong Redis hoặc in-process LRU.
- Invalidate khi có transaction CUD.
- Preaggregate daily totals → table `daily_stats` (category_id, date, sum) để query tháng/năm nhanh.
- Cập nhật `daily_stats` qua trigger hoặc batch job.

### Frontend
- Server Components cho phần static (card cấu trúc).
- Client Components cho interactive (chart, filter).
- React Query / SWR cho cache client.
- Skeleton placeholder < 100ms.
- Target: LCP < 1s trên laptop local.

## Responsive

- Desktop (≥1280): layout 2 cột như ở trên.
- Tablet (768–1279): 1 cột, card full width.
- Mobile (<768): KPI card 2x2, chart full, feed list nhỏ.
- Web app dùng qua Telegram inline browser cũng OK (hiếm dùng).

## Accessibility

- Không chỉ dùng màu: thêm icon / pattern cho màu đỏ/xanh.
- Keyboard nav toàn bộ: Tab, Enter, `/` focus search, `g d` go dashboard.
- Aria-label cho chart data point.

## Ưu tiên

| Section | MVP | Phase 2 |
|---|---|---|
| 1. KPI cards | ✅ | — |
| 2. Cashflow chart | ✅ | compare overlay |
| 3. Breakdown pie | ✅ | drill-down 3 level |
| 4. Budget progress | ✅ | — |
| 5. Top merchants/tags | ✅ cơ bản | tag chưa ưu tiên |
| 6. Accounts panel | ✅ | balance history detail |
| 7. Sankey flow | — | ✅ |
| 8. Transactions feed | ✅ | bulk action, saved view |
| 9. Filter sidebar | ✅ cơ bản | saved view |
| 10. Insight LLM | — | ✅ |
| 11. Goal tracker | — | ✅ |
| 12. Compare mode | — | ✅ |
