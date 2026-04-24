"""Redact sensitive info before sending to LLM (local or cloud)."""

from __future__ import annotations

import re

_CARD_RE = re.compile(r"\b(?:\d{4}[\s-]?){3,4}\d{1,4}\b")
_ACCT_RE = re.compile(r"\b\d{9,15}\b")
# OTP: keyword BEFORE the digits (e.g. "OTP: 123456", "mã xác thực 987654").
_OTP_RE = re.compile(
    r"(?i)(OTP|mã xác thực|verification(?:\s+code)?|security\s+code)(\s*[:\-]?\s*)(\d{4,8})\b"
)
# Balance line: keep key, redact value up to a terminator (newline or " — " or " | ").
_BALANCE_RE = re.compile(
    r"(?P<k>Số dư(?: tài khoản)?|Balance(?: after)?)\s*[:\-]?\s*[^\n\r|—]+",
    re.IGNORECASE,
)


def _mask_digits(s: str, keep_last: int = 4) -> str:
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]


def redact(text: str) -> str:
    if not text:
        return ""

    def card_sub(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return _mask_digits(digits)

    out = _CARD_RE.sub(card_sub, text)
    out = _ACCT_RE.sub(lambda m: _mask_digits(m.group(0)), out)
    out = _OTP_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}****", out)
    out = _BALANCE_RE.sub(lambda m: f"{m.group('k')}: [REDACTED]", out)
    return out
