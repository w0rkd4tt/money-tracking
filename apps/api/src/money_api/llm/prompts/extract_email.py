"""Prompt + schema for extracting a single transaction from an email."""

EXTRACT_EMAIL_SYSTEM_V1 = """Bạn là trợ lý trích xuất giao dịch tài chính từ email \
ngân hàng/ví điện tử/thẻ tín dụng (tiếng Việt hoặc Anh). Email đã được redact \
thông tin nhạy cảm (số thẻ/OTP/số dư chi tiết).

Quy tắc:
- is_transaction = true chỉ khi email báo 1 giao dịch CỤ THỂ (có số tiền + merchant/mô tả).
  false nếu là: OTP, mã xác thực, quảng cáo, newsletter, sao kê định kỳ tháng, \
  tin nhắn bảo mật, thông báo mở tài khoản.
- amount: số nguyên (không dấu chấm/phẩy) theo currency. VND không lẻ.
- kind: "expense" (chi tiêu, thanh toán, rút), "income" (ghi có, nhận tiền, hoàn tiền, lương),
  "transfer" (chuyển giữa 2 tài khoản của chính user).
- is_credit_card: true nếu email nói về thẻ tín dụng / credit card / dư nợ.
- account_hint: chọn đúng 1 tên account từ context; nếu không khớp, đoán theo sender
  (VD: HSBC, VCB, Techcombank, MB, Momo, Timo, ShopeePay).
- merchant: cửa hàng / đối tác / mục đích giao dịch (VD: "GS25 VN0037", \
  "Grab", "Shopee", "Tien phong tro"). \
  ƯU TIÊN đọc dòng "Mô tả:", "Description:", "Nội dung CK:", "Memo:" trong \
  body — đó là phần USER tự ghi, chính xác hơn tên tài khoản. KHÔNG dùng \
  tiêu đề chung như "Tài khoản Spend Account" / "Account Statement" làm \
  merchant. Với income như lương → merchant có thể là "Lương" hoặc null.
- category: chọn ĐÚNG 1 path từ danh sách "Category có sẵn" (định dạng \
  "Parent > Child", copy NGUYÊN VĂN cả khoảng trắng + dấu ">"). \
  Nếu không có path nào hợp lý → null. KHÔNG tự bịa category mới.
  Gợi ý mapping merchant → category: cafe/ăn/quán → "Ăn uống"; \
  Grab/taxi/xăng → "Đi lại"; Shopee/Lazada/cửa hàng → "Mua sắm"; \
  điện/nước/internet/bill → "Hoá đơn"; phòng trọ/tiền nhà/thuê nhà → \
  "Nhà ở > Tiền thuê" (hoặc "Nhà ở"); lương → "Lương"; refund/hoàn tiền → \
  "Hoàn tiền".
- ts: ISO 8601 có ĐẦY ĐỦ giờ/phút (VD: "2026-04-23T14:23:45"). Ưu tiên lấy từ \
  dòng thời gian giao dịch trong body (VD: "Thời gian: 14:23 23/04/2026"). \
  Nếu body chỉ có ngày, không có giờ → trả null cho ts (KHÔNG trả date-only \
  như "2026-04-23"); hệ thống sẽ tự dùng timestamp email nhận được.
- confidence: 0-1 phản ánh độ chắc chắn.
- Nếu không có giao dịch rõ ràng → is_transaction=false, các field khác null/0.

Trả về JSON duy nhất đúng schema. Không giải thích, không markdown."""


EXTRACT_EMAIL_SCHEMA = {
    "type": "object",
    "required": ["is_transaction"],
    "properties": {
        "is_transaction": {"type": "boolean"},
        "amount": {"type": "integer", "minimum": 0},
        "currency": {"type": "string"},
        "kind": {"type": "string", "enum": ["expense", "income", "transfer"]},
        "is_credit_card": {"type": "boolean"},
        "account_hint": {"type": ["string", "null"]},
        "merchant": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
        "ts": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": ["string", "null"]},
    },
}


def build_user_prompt(
    accounts: list[dict],
    sender: str,
    subject: str,
    body_redacted: str,
    now_iso: str,
    category_hints: list[str],
) -> str:
    import json as _json

    # Print the FULL category list (one per line) — truncating to 30 caused the
    # LLM to miss valid leaves like "Ăn uống > Cà phê" when the user has many
    # categories. The 80-cap is a safety against runaway DB content.
    cat_block = "\n".join(f"- {c}" for c in category_hints[:80])

    return f"""# Tài khoản của user
{_json.dumps(accounts, ensure_ascii=False, indent=2)}

# Category có sẵn (copy nguyên văn 1 path nếu phù hợp)
{cat_block}

# Thời điểm hiện tại
{now_iso}

# Email (đã redact thông tin nhạy cảm)
From: {sender}
Subject: {subject}
Body:
\"\"\"
{body_redacted[:2500]}
\"\"\"

Hãy phân tích email trên và trả về JSON đúng schema."""


# ---------------------------------------------------------------------------
# Lightweight category-only classifier — used when the rule engine already
# extracted amount/account/ts but didn't pick a category (most bank emails:
# the rule sets `category_hint="Chưa phân loại"` because banks don't tell you
# the merchant category, only the merchant name).
# ---------------------------------------------------------------------------

CLASSIFY_CATEGORY_SYSTEM_V1 = """Bạn phân loại 1 giao dịch tài chính vào danh \
mục (category) đã có sẵn dựa trên mô tả từ email + thông tin merchant.

Quy tắc:
- ƯU TIÊN đọc dòng "Mô tả:", "Nội dung:", "Memo:", "Description:" trong body \
— đó là USER tự ghi mục đích giao dịch, chính xác hơn merchant tên tài khoản.
- Chọn ĐÚNG 1 path từ danh sách "Category có sẵn", copy NGUYÊN VĂN cả \
khoảng trắng + dấu ">". Không bịa category mới.
- Mapping gợi ý: cafe/quán/ăn → "Ăn uống"; Grab/taxi/xăng → "Đi lại"; \
Shopee/Lazada/cửa hàng → "Mua sắm"; điện/nước/internet/bill → "Hoá đơn"; \
phòng trọ/tiền nhà/thuê nhà → "Nhà ở > Tiền thuê" (hoặc "Nhà ở"); \
refund/hoàn tiền → "Hoàn tiền"; lương/thưởng → "Lương"/"Thưởng".
- Nếu thật sự không có path phù hợp → null.
- Trả về JSON đúng schema {"category": "<path>|null"}. Không giải thích."""

CLASSIFY_CATEGORY_SCHEMA = {
    "type": "object",
    "required": ["category"],
    "properties": {
        "category": {"type": ["string", "null"]},
    },
}


def build_classify_user_prompt(
    sender: str,
    merchant: str | None,
    amount: int,
    kind: str,
    body_redacted: str,
    category_hints: list[str],
) -> str:
    cat_block = "\n".join(f"- {c}" for c in category_hints[:80])
    return f"""# Category có sẵn (chọn 1 hoặc null)
{cat_block}

# Giao dịch (đã trích từ rule engine)
sender: {sender}
merchant: {merchant or "(không rõ)"}
amount: {amount} ({kind})

# Body email (đã redact)
\"\"\"
{body_redacted[:1500]}
\"\"\"

Trả JSON {{"category": "<path>|null"}}."""
