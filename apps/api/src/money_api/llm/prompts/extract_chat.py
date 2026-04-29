EXTRACT_CHAT_SYSTEM_V1 = """Bạn là trợ lý ghi chép tài chính cá nhân tiếng Việt.
Nhiệm vụ: từ câu user, trích xuất danh sách giao dịch dưới dạng JSON.

Quy tắc:
- amount LUÔN là số nguyên VND (không chấm, không chữ "k","tr").
- "k" = 1000, "tr" = 1_000_000, "củ" = 1_000_000.
- Nếu không rõ ngày/giờ → dùng thời điểm hiện tại.
- account PHẢI khớp 1 trong danh sách tài khoản cho trước (case-insensitive).
- category: chọn ĐÚNG 1 path từ danh sách "Category có sẵn", copy NGUYÊN VĂN \
  cả khoảng trắng + dấu ">". KHÔNG bịa category mới; nếu không có path nào \
  hợp lý → null. Gợi ý mapping merchant → category: cafe/quán/ăn → "Ăn uống"; \
  Grab/taxi/xăng → "Đi lại"; Shopee/Lazada/cửa hàng → "Mua sắm"; \
  điện/nước/internet → "Hoá đơn"; phòng trọ/tiền nhà → "Nhà ở"; \
  lương/thưởng → "Lương"/"Thưởng".
- kind = "expense" mặc định; "income" nếu câu có "nhận", "lương", "thưởng", "refund";
  "transfer" nếu có "rút", "nạp", "chuyển", "sang X", "về Y".
- Với transfer: account=nguồn, to_account=đích.
- Nếu câu không chứa giao dịch → trả mảng rỗng.
- confidence: 0-1, mức chắc chắn.

Trả về JSON ĐÚNG schema, KHÔNG kèm text khác."""

EXTRACT_CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "amount",
                    "currency",
                    "kind",
                    "account",
                    "ts",
                    "confidence",
                ],
                "properties": {
                    "amount": {"type": "integer", "minimum": 0},
                    "currency": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["expense", "income", "transfer"],
                    },
                    "account": {"type": "string"},
                    "to_account": {"type": ["string", "null"]},
                    "category": {"type": ["string", "null"]},
                    "merchant": {"type": ["string", "null"]},
                    "ts": {"type": "string"},
                    "note": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
    "required": ["transactions"],
}


def build_user_prompt(
    text: str,
    accounts: list[dict],
    categories: list[str],
    merchants: list[str],
    now_iso: str,
) -> str:
    import json as _json

    cat_block = "\n".join(f"- {c}" for c in categories[:80])

    return f"""# Tài khoản
{_json.dumps(accounts, ensure_ascii=False, indent=2)}

# Category có sẵn (copy nguyên văn 1 path nếu phù hợp, hoặc null)
{cat_block}

# Merchant gần đây (top 20)
{", ".join(merchants[:20])}

# Thời điểm hiện tại
{now_iso}

# Câu của user
\"\"\"{text}\"\"\"
"""
