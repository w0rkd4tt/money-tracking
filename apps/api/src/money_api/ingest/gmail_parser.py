"""Rule-based parser: raw Gmail message → ParsedTransaction.

Rules are tried in priority order. First match wins. Each rule extracts
amount, timestamp, merchant, account_hint from headers/body.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime

from ..llm.redact import redact

log = logging.getLogger(__name__)


@dataclass
class RawEmail:
    message_id: str
    from_addr: str
    subject: str
    body_text: str
    received_at: datetime | None = None


@dataclass
class ParsedTx:
    amount: Decimal  # absolute value (sign derived from kind)
    currency: str = "VND"
    kind: str = "expense"  # expense | income | transfer
    merchant: str | None = None
    account_hint: str | None = None  # e.g. "VCB", "Momo" from rule
    is_credit_card: bool = False  # True → goes to credit account; spend = debt ↑
    note: str | None = None
    ts: datetime | None = None
    rule_name: str = ""
    confidence: float = 0.9
    # Category path ("Parent > Child") from LLM extraction, or leaf name from a
    # rule. `ingest_parsed` resolves this to a `category_id` if it matches a row;
    # unknowns fall back to the per-kind default so nothing blocks ingestion.
    category: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Rule:
    name: str
    sender_globs: list[str]
    subject_any: list[str]  # case-insensitive contains
    account_hint: str
    amount_patterns: list[str]  # regex with group(1) = amount
    # Sign detection: if the first match has a leading sign-group, use it.
    # Otherwise fall back to keywords.
    merchant_patterns: list[str] = field(default_factory=list)
    income_keywords: list[str] = field(default_factory=list)
    expense_keywords: list[str] = field(default_factory=list)
    transfer_keywords: list[str] = field(default_factory=list)
    credit_card_keywords: list[str] = field(default_factory=list)  # → is_credit_card=True
    ts_patterns: list[str] = field(default_factory=list)  # parse to datetime
    # Optional default category path (or leaf name) that ingest_parsed will try to
    # resolve — gives rule hits a starting category instead of NULL. The LLM
    # fallback path populates `ParsedTx.category` from the model output instead.
    category_hint: str | None = None
    priority: int = 100
    is_credit_card: bool = False  # whole rule targets a credit card account


def _match_glob(pattern: str, value: str) -> bool:
    # Minimal glob: * → .*
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.match(regex, value, re.IGNORECASE) is not None


def _parse_amount(raw: str) -> Decimal | None:
    """Normalize VN amounts: "1.234.567" → 1234567, "1,234,567.00" → 1234567.00."""
    s = raw.strip()
    # If contains comma AND dot → assume US style (1,234.56)
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "." in s and "," not in s:
        # VN style: dots as thousand separator if no decimal part (common)
        parts = s.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            s = s.replace(".", "")
    elif "," in s:
        parts = s.split(",")
        if all(len(p) == 3 for p in parts[1:]):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def _extract_ts(raw: str, fallback: datetime | None) -> datetime | None:
    raw = raw.strip()
    for fmt in (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return fallback


_SIGN_NEAR_RE = re.compile(
    r"(?:(?P<pre>[+\-])\s*[\d,\.]+)|(?:[\d,\.]+\s*(?P<suf>[+\-]))"
)


def _detect_kind_and_credit(
    rule: Rule, email: RawEmail, leading_sign: str | None
) -> tuple[str, bool]:
    """Return (kind, is_credit_card) given rule + email text.

    Priority:
      1. Explicit keywords (transfer > income > credit_card > expense)
      2. Leading sign on amount match (+ → income, - → expense)
      3. Default = expense
    """
    text = (email.subject + "\n" + email.body_text).lower()

    def any_match(kws: list[str]) -> bool:
        return any(re.search(k.lower(), text) for k in kws)

    is_cc = rule.is_credit_card or any_match(rule.credit_card_keywords)

    if any_match(rule.transfer_keywords):
        return "transfer", is_cc
    if any_match(rule.income_keywords):
        return "income", is_cc
    if any_match(rule.expense_keywords):
        return "expense", is_cc
    if leading_sign == "+":
        return "income", is_cc
    if leading_sign == "-":
        return "expense", is_cc
    return "expense", is_cc


def apply_rule(rule: Rule, email: RawEmail) -> ParsedTx | None:
    if not any(_match_glob(g, email.from_addr) for g in rule.sender_globs):
        return None
    subj = email.subject.lower()
    if rule.subject_any and not any(k.lower() in subj for k in rule.subject_any):
        return None

    body = email.body_text
    # Extract amount + capture leading sign if present in context
    amount: Decimal | None = None
    leading_sign: str | None = None
    for pat in rule.amount_patterns:
        m = re.search(pat, body, re.IGNORECASE | re.MULTILINE)
        if m:
            amount = _parse_amount(m.group(1))
            if amount is not None:
                # Look 20 chars before/after the match for a sign hint
                window = body[max(0, m.start() - 20) : m.end() + 5]
                sm = _SIGN_NEAR_RE.search(window)
                if sm:
                    leading_sign = sm.group("pre") or sm.group("suf")
                break
    if amount is None:
        return None

    merchant: str | None = None
    for pat in rule.merchant_patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            merchant = m.group(1).strip()
            if merchant:
                break

    ts: datetime | None = None
    for pat in rule.ts_patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            ts = _extract_ts(m.group(1), email.received_at)
            if ts:
                break
    if ts is None:
        ts = email.received_at

    kind, is_cc = _detect_kind_and_credit(rule, email, leading_sign)

    return ParsedTx(
        amount=amount,
        currency="VND",
        kind=kind,
        merchant=merchant,
        account_hint=rule.account_hint,
        is_credit_card=is_cc,
        ts=ts,
        note=redact(email.subject)[:200],
        rule_name=rule.name,
        confidence=0.9,
        category=rule.category_hint,
        extra={"sender": email.from_addr, "message_id": email.message_id, "sign": leading_sign},
    )


# --- Built-in rule templates for common Vietnamese banks & wallets ----------
# These are starting points; users can refine via /api/v1/rules endpoints.
BUILTIN_RULES: list[Rule] = [
    Rule(
        name="VCB-credit-card",
        sender_globs=[
            "*@vcbonline.com.vn",
            "*@info.vietcombank.com.vn",
            "*@vietcombank.com.vn",
        ],
        subject_any=["the tin dung", "thẻ tín dụng", "credit card"],
        account_hint="VCB Credit",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
            r"GD\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
        ],
        merchant_patterns=[
            r"n[ộo]i\s*dung\s*:?\s*(.+?)(?:\r?\n|$)",
            r"t[ạa]i\s*(.+?)(?:\r?\n|$)",
        ],
        ts_patterns=[r"Th[ờo]i\s*gian\s*:?\s*([\d/\-:\s]+)"],
        is_credit_card=True,
        credit_card_keywords=["the tin dung", "thẻ tín dụng", "credit card"],
        income_keywords=["thanh toan sao ke", "thanh toan the", "ho[àa]n ti[ềe]n"],
        # Credit card spend → "Chưa phân loại" so user can re-classify in UI.
        # Specific sub-categories (food/shopping) should come from LLM fallback.
        category_hint="Chưa phân loại",
        priority=200,  # matched before regular VCB rule
    ),
    Rule(
        name="VCB",
        sender_globs=[
            "*@vcbonline.com.vn",
            "*@info.vietcombank.com.vn",
            "*@vietcombank.com.vn",
        ],
        subject_any=["giao dich", "bien dong so du", "vcb digibank", "thong bao"],
        account_hint="VCB",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
            r"GD\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
        ],
        merchant_patterns=[
            r"n[ộo]i\s*dung\s*:?\s*(.+?)(?:\r?\n|$)",
            r"t[ạa]i\s*(.+?)(?:\r?\n|$)",
        ],
        ts_patterns=[r"Th[ờo]i\s*gian\s*:?\s*([\d/\-:\s]+)"],
        income_keywords=["ghi co", "ghi có", "nhan tien", "nhận tiền", "\\+ti[ềe]n"],
        expense_keywords=["ghi no", "ghi nợ", "chi tieu", "chi tiêu", "thanh toan", "rut tien"],
        priority=100,
    ),
    Rule(
        name="Techcombank",
        sender_globs=["*@techcombank.com.vn"],
        subject_any=["giao dich", "bien dong so du", "thong bao"],
        account_hint="TCB",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
        ],
        merchant_patterns=[r"n[ộo]i\s*dung\s*:?\s*(.+?)(?:\r?\n|$)"],
        ts_patterns=[r"th[ờo]i\s*gian\s*:?\s*([\d/\-:\s]+)"],
        income_keywords=["ghi co", "ghi có"],
        priority=100,
    ),
    Rule(
        name="MB",
        sender_globs=["*@mbbank.com.vn"],
        subject_any=["giao dich", "bien dong"],
        account_hint="MB",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
        ],
        merchant_patterns=[r"n[ộo]i\s*dung\s*:?\s*(.+?)(?:\r?\n|$)"],
        income_keywords=["ghi co"],
        priority=100,
    ),
    Rule(
        name="TPBank",
        sender_globs=["*@tpb.vn", "*@tpb.com.vn"],
        subject_any=["giao dich", "bien dong", "thong bao"],
        account_hint="TPB",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)",
        ],
        merchant_patterns=[r"n[ộo]i\s*dung\s*:?\s*(.+?)(?:\r?\n|$)"],
        income_keywords=["ghi co"],
        priority=100,
    ),
    Rule(
        name="Momo",
        sender_globs=["*@momo.vn", "*@mservice.com.vn"],
        subject_any=["giao dich", "thanh toan", "nap tien", "thong bao"],
        account_hint="Momo",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*:?\s*(?:VND|\+|\-)?\s*([\d,\.]+)\s*(?:đ|VND|₫)",
            r"(?:\+|\-)\s*([\d,\.]+)\s*(?:đ|VND|₫)",
        ],
        merchant_patterns=[
            r"(?:n[ộo]i\s*dung|m[ôo]\s*t[ảa])\s*:?\s*(.+?)(?:\r?\n|$)",
        ],
        ts_patterns=[r"th[ờo]i\s*gian\s*:?\s*([\d/\-:\s]+)"],
        income_keywords=["nh[ậa]n ti[ềe]n", "ho[àa]n ti[ềe]n", "refund", "ghi co"],
        transfer_keywords=["chuy[ểe]n ti[ềe]n v[ềe]", "n[ạa]p ti[ềe]n v[àa]o"],
        priority=100,
    ),
    Rule(
        name="Shopee",
        sender_globs=["*@shopee.vn", "*@shopeepay.vn"],
        subject_any=["don hang", "thanh toan", "xac nhan"],
        account_hint="ShopeePay",
        amount_patterns=[
            r"t[ổo]ng\s*c[ộo]ng\s*:?\s*([\d,\.]+)",
            r"t[ổo]ng\s*ti[ềe]n\s*:?\s*([\d,\.]+)",
        ],
        merchant_patterns=[r"(?:shop|ng[ườ]i\s*b[áa]n)\s*:?\s*(.+?)(?:\r?\n|$)"],
        priority=80,
    ),
    # Timo digital bank (BVBank). Email format:
    # "Tài khoản Spend Account vừa giảm 5.000.000 VND vào 02/04/2026 21:21."
    # "Tài khoản ... vừa tăng X VND ..."
    Rule(
        name="Timo",
        sender_globs=["*@timo.vn", "*@bvbank.vn"],
        subject_any=["thay doi so du", "thay đổi số dư", "bien dong", "biến động"],
        account_hint="Timo",
        amount_patterns=[
            r"v[ừu]a\s*(?:gi[ảa]m|t[ăa]ng)\s*([\d\.,]+)\s*VND",
            r"s[ốo]\s*ti[ềe]n\s*:?\s*([\d\.,]+)\s*VND",
        ],
        merchant_patterns=[
            r"M[ôo]\s*t[ảa]\s*:?\s*(.+?)(?:\r?\n|$)",
        ],
        ts_patterns=[r"v[àa]o\s*([\d/]+\s*[\d:]+)"],
        income_keywords=[r"v[ừu]a\s*t[ăa]ng", r"ghi co", r"nh[ậa]n ti[ềe]n"],
        expense_keywords=[r"v[ừu]a\s*gi[ảa]m", r"chuy[ểe]n ti[ềe]n", r"thanh to[áa]n"],
        # Timo bank movement — default to uncategorized so it shows up in UI
        # triage. Transfers between own accounts get auto-categorized by
        # _resolve_category_for(kind="transfer") which wins over this hint.
        category_hint="Chưa phân loại",
        priority=110,
    ),
    # HSBC credit card transaction alert. Forwarded email typically contains:
    # "thẻ tín dụng X2586 ... giao dịch với số tiền 37,000 VND tại GS25 VN0037 OCB"
    # "Dư nợ hiện tại là 2,075,048 VND"
    Rule(
        name="HSBC-credit-card",
        sender_globs=[
            "*@hsbc.com.vn",
            "*@hsbc.com.hk",
            "*@notification.hsbc.com.vn",
            "*@notification.hsbc.com.hk",
        ],
        subject_any=["hsbc", "thẻ td hsbc", "the td hsbc", "credit card"],
        account_hint="HSBC",
        amount_patterns=[
            r"s[ốo]\s*ti[ềe]n\s*([\d,\.]+)\s*VND",
            r"VND\s*([\d,\.]+)",
            r"charged\s*VND\s*([\d,\.]+)",
        ],
        merchant_patterns=[
            r"t[ạa]i\s+(.+?)\s+v[àa]o\s+ng[àa]y",
            r"at\s+merchant\s+(.+?)\s+on",
        ],
        ts_patterns=[r"v[àa]o\s*ng[àa]y\s*([\d/]+)", r"on\s*([\d/]+)"],
        is_credit_card=True,
        credit_card_keywords=["th[ẻe]\\s*t[íi]n\\s*d[ụu]ng", "credit\\s*card"],
        category_hint="Chưa phân loại",
        priority=220,
    ),
]


def parse_email(email: RawEmail, rules: list[Rule] | None = None) -> ParsedTx | None:
    """Try each rule in priority order; return first match."""
    rules = rules or sorted(BUILTIN_RULES, key=lambda r: -r.priority)
    for r in rules:
        out = apply_rule(r, email)
        if out is not None:
            log.debug("matched rule %s for %s", r.name, email.from_addr)
            return out
    return None


# --- Gmail message → RawEmail --------------------------------------------
_FORWARD_FROM_RE = re.compile(
    # Supports both "From: Display Name <email@x.y>" and "From: email@x.y"
    r"(?:^|\n)\s*(?:T[ừu]|From)\s*:\s*"
    r"(?:[^\r\n<]*<([^>\s]+@[^>\s]+)>|([^\s<>@]+@[^\s<>]+))",
    re.IGNORECASE | re.MULTILINE,
)
_FORWARD_SUBJ_RE = re.compile(
    r"(?:^|\n)\s*(?:Ch[ủu]\s*[đd][ềe]|Subject|Ti[êe]u\s*[đd][ềe])\s*:\s*([^\r\n]+)",
    re.IGNORECASE | re.MULTILINE,
)
# Strong forwarded-email markers across common mail clients.
_FORWARD_MARKER_RE = re.compile(
    r"(?:-{3,}\s*Forwarded\s+message|"
    r"Begin\s+forwarded\s+message|"
    r"-{3,}\s*Original\s+Message|"
    r"-{3,}\s*Đã\s*chuy[ểe]n\s*ti[ếe]p|"
    r"-{3,}\s*Tin\s*nh[ắa]n\s*chuy[ểe]n\s*ti[ếe]p|"
    r"Forwarded\s+by\s+)",
    re.IGNORECASE,
)


def looks_forwarded(subject: str, body: str) -> bool:
    """Detect forwarded emails without relying only on 'Fwd:' subject prefix.

    Signals (any):
      1. Subject prefix (EN/FR/VN variants)
      2. Body contains a client-standard forwarded marker
      3. Body contains a From:/Từ: header line in the first 2KB (indicates quoted headers)
    """
    s = (subject or "").strip().lower()
    for pref in ("fwd:", "fw:", "trs:", "tr:", "vs:", "rv:", "đã chuyển tiếp:"):
        if s.startswith(pref):
            return True
    head = (body or "")[:2000]
    if _FORWARD_MARKER_RE.search(head):
        return True
    if _FORWARD_FROM_RE.search(head):
        return True
    return False


def _extract_forwarded(body: str) -> tuple[str | None, str | None]:
    """Return (original_sender_email, original_subject) from forwarded body.

    If a marker line is present, search only after it (safer — avoids picking
    up From: from quoted-reply chains). Otherwise search the whole head.
    """
    head = body[:5000] if body else ""
    marker = _FORWARD_MARKER_RE.search(head)
    region = head[marker.end():] if marker else head

    sender = None
    subject = None
    m = _FORWARD_FROM_RE.search(region)
    if m:
        # Either bracketed group or bare email group
        sender = (m.group(1) or m.group(2) or "").strip().lower()
    m2 = _FORWARD_SUBJ_RE.search(region)
    if m2:
        subject = m2.group(1).strip()
    return sender, subject


def raw_email_from_gmail(msg: dict) -> RawEmail:
    """Convert a Gmail `messages.get` full-format dict into RawEmail.

    For **forwarded** emails, overrides from_addr (and subject) with values
    extracted from the body — so rule matching works against the bank's real
    sender rather than whoever forwarded the message. Detection does NOT rely
    on the 'Fwd:' subject prefix alone; it also checks for standard forwarded
    markers and for quoted From: headers.
    """
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _walk_body(msg.get("payload", {}))
    received = None
    if "date" in headers:
        try:
            received = parsedate_to_datetime(headers["date"]).replace(tzinfo=None)
        except Exception:
            received = None
    # Gmail's `internalDate` (ms since epoch) is always populated — use it as
    # the fallback when the Date: header is missing or malformed (some bank
    # senders emit non-RFC-2822 dates and parsedate_to_datetime returns None).
    if received is None and msg.get("internalDate"):
        try:
            from datetime import timezone
            from zoneinfo import ZoneInfo

            from ..config import get_settings

            ms = int(msg["internalDate"])
            tz = ZoneInfo(get_settings().tz)
            received = (
                datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
                .astimezone(tz)
                .replace(tzinfo=None)
            )
        except Exception:
            received = None

    from_addr = headers.get("from", "")
    subject = headers.get("subject", "")
    if looks_forwarded(subject, body):
        fwd_from, fwd_subj = _extract_forwarded(body)
        if fwd_from:
            from_addr = fwd_from
        if fwd_subj:
            subject = fwd_subj

    return RawEmail(
        message_id=msg.get("id", ""),
        from_addr=from_addr,
        subject=subject,
        body_text=body,
        received_at=received,
    )


def _walk_body(part: dict) -> str:
    import base64

    mime = part.get("mimeType", "")
    if part.get("parts"):
        chunks = [_walk_body(p) for p in part["parts"]]
        return "\n".join(c for c in chunks if c)
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""
    if mime == "text/html":
        # Strip HTML tags minimally
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw)
    return raw
