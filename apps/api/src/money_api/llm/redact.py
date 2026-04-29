"""Redact sensitive info before sending to LLM (local or cloud)."""

from __future__ import annotations

import re

# Email "chrome" — greeting + signature/marketing tail. Strips noise so the
# rule's merchant regex doesn't eat the signature into merchant_text and
# the LLM context stays tight (faster on Ollama 9B + less prompt confusion).
#
# Crucially: we DON'T require \n boundaries because Gmail's plain-text
# representation is often a single line (HTML→text conversion collapses
# newlines), so the entire greeting + body + signature lives on one line.
_GREETING_RE = re.compile(
    r"^.{0,80}?\b(?:thân mến|kính gửi|dear|hello|xin chào)\b[,\s]*",
    re.IGNORECASE | re.DOTALL,
)
_SIGNATURE_RE = re.compile(
    r"[\s.]*\b(?:Cảm ơn|Thank you|Trân trọng|Best regards|Regards|Sincerely)"
    r"[\s\S]*$",
    re.IGNORECASE,
)

_CARD_RE = re.compile(r"\b(?:\d{4}[\s-]?){3,4}\d{1,4}\b")
_ACCT_RE = re.compile(r"\b\d{9,15}\b")
# OTP: keyword BEFORE the digits (e.g. "OTP: 123456", "mã xác thực 987654").
_OTP_RE = re.compile(
    r"(?i)(OTP|mã xác thực|verification(?:\s+code)?|security\s+code)(\s*[:\-]?\s*)(\d{4,8})\b"
)
# Balance line: keep key, redact ONLY the numeric amount (+ optional VND/USD
# unit). Earlier we ate everything up to a newline / pipe / em-dash, but bank
# emails are often a single line where "Số dư hiện tại: X VND. Mô tả: ..."
# all sit together — that swallowed the description and the LLM lost the
# signal it needed for categorisation.
_BALANCE_RE = re.compile(
    r"(?P<k>Số dư(?:\s+(?:tài khoản|hiện tại|khả dụng))?|Balance(?:\s+after)?)"
    r"\s*[:\-]?\s*"
    r"[\d.,]+\s*(?:VND|USD|đ|₫)?",
    re.IGNORECASE,
)


def _mask_digits(s: str, keep_last: int = 4) -> str:
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]


def strip_chrome(text: str) -> str:
    """Remove email greeting + signature/marketing tail.

    Bank emails are dominated by polite chrome ("XYZ thân mến", "Cảm ơn quý
    khách... Trân trọng, Timo Digital Bank"). Stripping it before redact
    cuts the prompt by 50–80%, letting the local 9B model respond inside the
    timeout instead of dying with "Ollama unavailable".
    """
    if not text:
        return ""
    out = _GREETING_RE.sub("", text)
    out = _SIGNATURE_RE.sub("", out)
    return out.strip()


def redact(text: str) -> str:
    if not text:
        return ""
    # Strip chrome BEFORE redact so signature lines (which can contain bank
    # names / contact info) don't end up half-redacted in the prompt.
    text = strip_chrome(text)

    def card_sub(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return _mask_digits(digits)

    out = _CARD_RE.sub(card_sub, text)
    out = _ACCT_RE.sub(lambda m: _mask_digits(m.group(0)), out)
    out = _OTP_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}****", out)
    out = _BALANCE_RE.sub(lambda m: f"{m.group('k')}: [REDACTED]", out)
    return out
