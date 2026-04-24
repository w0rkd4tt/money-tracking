# 06 — Chiến lược LLM

## Mục tiêu

1. Trích xuất giao dịch từ câu tự nhiên / email với schema cố định.
2. Phân loại giao dịch vào category cây đã có.
3. Sinh văn bản insight & báo cáo.
4. Giữ chi phí thấp & privacy an toàn.

## Hai luồng: Extract (fast) vs Agent (ReAct)

Không phải mọi chat turn đều cần agent. Router phân luồng:

- **Fast path**: user khai báo giao dịch → structured output trực tiếp từ model, < 1s. Không tool.
- **Agent path**: user hỏi, cần truy vấn DB / Gmail → LangGraph ReAct agent với tool calling.

Chi tiết tools, policy, Langfuse tracing: xem [14-llm-tools.md](./14-llm-tools.md).

## Kiến trúc Provider

Router quản lý **named providers** — mỗi provider là 1 endpoint + model + timeout cụ thể. Không hard-code "ollama" hay "deepseek" trong business logic; business logic chỉ chỉ định *task*, Router resolve ra provider.

### Providers mặc định

| Tên | Loại | URL | Model | Dùng cho |
|---|---|---|---|---|
| `m1ultra` | ollama | `http://127.0.0.1:11434` | `jaahas/qwen3.5-uncensored:9b` | mọi task local |
| `m1ultra.embed` | ollama | cùng instance | `nomic-embed-text` | embedding |
| `deepseek` | openai-compatible | `https://api.deepseek.com` | `deepseek-chat` | cloud fallback, opt-in |

### Interface provider (Python)

```python
class LLMProvider(Protocol):
    name: str
    async def chat(
        self, messages: list[dict], *,
        schema: dict | None = None,        # JSON schema ép output
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class OllamaProvider(LLMProvider):
    """Dùng cho m1ultra và mọi instance Ollama khác (home server, LAN)."""

class OpenAICompatibleProvider(LLMProvider):
    """Dùng cho DeepSeek, hoặc provider cloud khác tương thích OpenAI API."""
```

Config provider load từ env tại boot, inject vào Router.

## Task routing

```
┌──────────────────────────────────────────────────────────────┐
│                       Task → Provider + mode                  │
├──────────────────────────────────────────────────────────────┤
│  extract_chat (fast)  → m1ultra  (JSON schema, no tools)      │
│  agent_chat           → m1ultra agent model + ReAct tools     │
│  extract_email_easy   → Regex rule (no LLM)                   │
│  extract_email_hard   → m1ultra → fallback deepseek           │
│  classify_category    → embedding kNN → fallback m1ultra      │
│  weekly_digest        → m1ultra (nếu ≥14B) hoặc deepseek      │
│  anomaly_explain      → m1ultra                               │
└──────────────────────────────────────────────────────────────┘
```

`agent_chat` dùng **model khác** (`M1ULTRA_AGENT_MODEL=qwen2.5:7b-instruct`) vì uncensored finetune có thể phá vỡ tool calling. Xem [14-llm-tools.md](./14-llm-tools.md#model-cho-agent).

### Quy tắc routing
1. **Mặc định dùng provider local (`m1ultra`).** Chỉ fallback sang cloud khi:
   - Local model trả `confidence < 0.6` hoặc JSON invalid 2 lần liên tiếp.
   - Input phức tạp (email HTML dài, nhiều giao dịch lồng nhau).
   - User bật flag "cloud mode" trong settings.
2. **Trước khi gọi cloud: redact**
   - Số thẻ (regex `\d{12,19}` → `****XXXX`, giữ 4 số cuối).
   - STK full → giữ 4 số cuối.
   - Email/SĐT riêng tư trong body (nếu có).
   - OTP (đôi khi lẫn trong email).
3. **Log mọi call** vào `logs/llm.jsonl`: model, prompt, response, latency, cost estimate.

## Prompt templates

Tất cả prompt có **version**; tăng version khi đổi, log kèm để reproduce được.

### 6.1 Extract từ chat (`extract_chat@v1`)

**System:**
```
Bạn là trợ lý ghi chép tài chính cá nhân tiếng Việt.
Nhiệm vụ: từ câu user, trích xuất danh sách giao dịch dưới dạng JSON.

Quy tắc:
- amount LUÔN là số nguyên VND (không chấm, không chữ "k","tr").
- "k" = 1000, "tr" = 1_000_000, "củ" = 1_000_000.
- Nếu không rõ ngày/giờ → dùng thời điểm hiện tại.
- account PHẢI khớp 1 trong danh sách tài khoản cho trước (case-insensitive, có alias).
- category dùng đường dẫn cây "Parent > Child". Nếu không chắc → "Chưa phân loại".
- kind = "expense" mặc định, "income" nếu câu có "nhận", "lương", "thưởng", "refund".
- Nếu câu không chứa giao dịch → trả mảng rỗng.
- confidence: 0-1, phản ánh mức chắc chắn của BẠN.

Trả về JSON ĐÚNG schema, KHÔNG kèm text khác.
```

**User template:**
```
# Tài khoản
{accounts_json}

# Category cây (rút gọn)
{categories_json}

# Merchant gần đây (top 20)
{recent_merchants}

# Thời điểm hiện tại
{now_iso}

# Câu của user
"{user_text}"
```

**Response schema (Ollama `format`):**
```json
{
  "type": "object",
  "properties": {
    "transactions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["amount","currency","kind","account","ts","confidence"],
        "properties": {
          "amount": {"type":"integer","minimum":0},
          "currency": {"type":"string","enum":["VND","USD"]},
          "kind": {"type":"string","enum":["expense","income","transfer"]},
          "account": {"type":"string"},
          "to_account": {"type":["string","null"]},
          "category": {"type":["string","null"]},
          "merchant": {"type":["string","null"]},
          "ts": {"type":"string","format":"date-time"},
          "note": {"type":["string","null"]},
          "confidence": {"type":"number","minimum":0,"maximum":1}
        }
      }
    }
  },
  "required": ["transactions"]
}
```

**Ví dụ few-shot (đính kèm trong system):**
```
Input: "sáng cafe 25k, trưa cơm 50k"
Output: {"transactions":[
  {"amount":25000,"currency":"VND","kind":"expense","account":"Tiền mặt",
   "category":"Ăn uống > Sáng","merchant":"cafe",
   "ts":"2026-04-21T07:00:00+07:00","confidence":0.75},
  {"amount":50000,"currency":"VND","kind":"expense","account":"Tiền mặt",
   "category":"Ăn uống > Trưa","merchant":null,
   "ts":"2026-04-21T12:00:00+07:00","confidence":0.85}
]}

Input: "lương về 25tr"
Output: {"transactions":[
  {"amount":25000000,"currency":"VND","kind":"income",
   "account":"<account lương mặc định>", "category":"Lương",
   "ts":"<now>","confidence":0.9}
]}
```

### 6.2 Extract từ email (`extract_email@v1`)

**System:**
```
Trích xuất giao dịch tài chính từ email ngân hàng/ví điện tử.
Email có thể bằng tiếng Việt hoặc Anh.
Ưu tiên lấy: amount, currency, account (số cuối thẻ/STK), merchant, ts (giờ giao dịch trong email, KHÔNG phải ngày gửi email), balance_after (nếu có).
Nếu email không phải thông báo giao dịch (OTP, marketing, sao kê định kỳ) → trả {"is_transaction": false}.
```

**Redaction trước khi gửi cloud:**
- Thay STK/số thẻ bằng `****<last4>`.
- Xoá số dư tài khoản nếu có (không cần cho extract, lộ thông tin).
- Xoá OTP (6-8 chữ số liền).

### 6.3 Classify category (`classify@v1`)

**Chiến lược rẻ trước:**
1. Tìm merchant trong `merchant` table → nếu có `default_category_id` → xong.
2. Embedding câu mô tả giao dịch + kNN trên 100 giao dịch gần nhất → nếu similarity > 0.85 → copy category.
3. Nếu vẫn không → gọi LLM classify với prompt ngắn:
   ```
   Giao dịch: "{merchant}, {note}, {amount}"
   Chọn 1 category (chỉ in ra đường dẫn):
   {categories_tree}
   ```

### 6.4 Weekly digest (`digest@v1`)

Input: aggregated stats (đã tính trong code, không cho LLM làm math).
```
Viết báo cáo tuần ngắn (≤120 từ), tiếng Việt, phong cách thân thiện.
Dữ liệu:
- Tổng chi tuần này: {total}
- So với tuần trước: {delta_pct}%
- Top 3 category: {top}
- Giao dịch bất thường: {anomalies}
- Budget status: {budget}

Gợi ý 1 hành động cụ thể (không nói chung chung).
Không dùng emoji quá 2 cái.
```

## Structured output — cách ép JSON với Ollama (`m1ultra`)

```python
import httpx, os

resp = httpx.post(
    f"{os.environ['M1ULTRA_URL']}/api/chat",
    timeout=int(os.environ.get("M1ULTRA_TIMEOUT", "120")),
    json={
        "model": os.environ["M1ULTRA_MODEL"],
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_PROMPT},
        ],
        "format": EXTRACT_SCHEMA,   # JSON schema object
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512}
    }
)
data = resp.json()["message"]["content"]  # valid JSON string
parsed = pydantic_model.model_validate_json(data)
```

Model uncensored như `jaahas/qwen3.5-uncensored:9b` vẫn tôn trọng `format` JSON schema bình thường. Nếu đổi model thấy JSON hay vỡ, giảm `temperature` = 0 + retry 1 lần trước khi fallback cloud.

Fallback khi JSON invalid:
1. Retry 1 lần với `temperature = 0`.
2. Vẫn fail → gọi DeepSeek (nếu được phép).
3. Vẫn fail → trả lỗi cho user: "chưa hiểu, bạn nói rõ hơn được không?".

## Context building

Trước mỗi call, assemble context nhỏ gọn (tránh nhét cả DB):

| Loại | Giới hạn |
|---|---|
| Accounts | tất cả (thường < 10) |
| Categories | rút gọn: chỉ leaf + parent, max 100 dòng. Nếu vượt thì 2 tầng. |
| Recent merchants | top 20 trong 30 ngày qua |
| Recent chat messages | 10 turn gần nhất trong session |
| Time now | ISO 8601 với TZ `+07:00` |

Tổng context target: **< 2000 tokens** cho `m1ultra` (giữ tốc độ inference), **< 4000** nếu fallback DeepSeek.

## Chi phí & giới hạn

### Ước tính DeepSeek
- DeepSeek V3: ~ $0.27/1M input, $1.10/1M output.
- Extract 1 email: ~1500 input + 200 output ≈ $0.0006 = ~15 VND.
- 50 email/ngày × 30 ngày = 1500 call ≈ 22.500 VND/tháng. Không đáng kể.

### Budget hard cap
- `LLM_CLOUD_MONTHLY_BUDGET_USD` (env), mặc định $5.
- Khi đạt 80% → warn Telegram.
- Đạt 100% → tắt fallback cloud, chỉ dùng local.

## Đánh giá chất lượng

Tạo bộ test tĩnh `tests/llm_goldens.jsonl`:
```json
{"input":"trưa nay ăn phở 45k bằng momo","expected":{...}}
{"input":"lương 25tr","expected":{...}}
```
- Mỗi lần đổi prompt → chạy golden test, so sánh field-by-field (amount exact, category path match).
- CI: nếu pass rate < 90% → fail.

## Pitfall cần tránh

1. **LLM bịa số tiền**: ép prompt "amount là số nguyên từ INPUT, không suy luận". Luôn cross-check bằng regex số trong input, nếu LLM đưa số không có trong input → reject.
2. **LLM bịa category không tồn tại**: sau parse, map về leaf gần nhất bằng string similarity. Nếu không match > 0.7 → dùng "Chưa phân loại".
3. **Ambiguity "k"**: "45k" = 45000 trong VN context, nhưng cũng có thể hiểu "45000000" nếu user lười. Quy ước cứng trong prompt, và nếu amount > 10tr + confidence < 0.8 → confirm lại.
4. **Timezone**: Ollama model thường trả UTC. Chuẩn hoá về `Asia/Ho_Chi_Minh` ở backend.
5. **Multi-language contamination**: user mix tiếng Anh. Prompt phải nói rõ "accept Vietnamese and English".
