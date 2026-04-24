"""Rule parser tests with synthetic bank emails."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_api.ingest.gmail_parser import RawEmail, parse_email, raw_email_from_gmail


def _email(from_addr: str, subject: str, body: str) -> RawEmail:
    return RawEmail(
        message_id="m1",
        from_addr=from_addr,
        subject=subject,
        body_text=body,
        received_at=datetime(2026, 4, 22, 12, 0, 0),
    )


def test_parse_vcb_expense():
    body = """Kinh gui Quy khach,
Thong tin giao dich tren tai khoan **1234:
So tien: -450.000 VND
Noi dung: THANH TOAN TAI GRAB HCM
Thoi gian: 22/04/2026 12:30
"""
    parsed = parse_email(_email("no-reply@vcbonline.com.vn", "VCB Digibank - Thong bao giao dich", body))
    assert parsed is not None
    assert parsed.rule_name == "VCB"
    assert parsed.amount == Decimal("450000")
    assert parsed.kind == "expense"
    assert "GRAB" in (parsed.merchant or "").upper()
    assert parsed.account_hint == "VCB"


def test_parse_vcb_income():
    body = """So tien: +10.000.000 VND
Noi dung: LUONG THANG 4
Ghi co tai khoan"""
    parsed = parse_email(_email("no-reply@vcbonline.com.vn", "Thong bao giao dich - ghi co", body))
    assert parsed is not None
    assert parsed.kind == "income"
    assert parsed.amount == Decimal("10000000")


def test_parse_momo():
    body = """Momo da ghi nhan giao dich cua ban.
So tien: -35.000 đ
Mo ta: Thanh toan Grab
Thoi gian: 22/04/2026 12:15"""
    parsed = parse_email(_email("noreply@momo.vn", "Thong bao thanh toan Momo", body))
    assert parsed is not None
    assert parsed.rule_name == "Momo"
    assert parsed.amount == Decimal("35000")
    assert parsed.account_hint == "Momo"


def test_unknown_sender_returns_none():
    parsed = parse_email(_email("marketing@random.com", "Sale!", "Flash sale 50% off"))
    assert parsed is None


def test_raw_email_from_gmail_decodes_plain_body():
    import base64

    body = "So tien: -45.000 VND\nNoi dung: Pho bo"
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    msg = {
        "id": "abc",
        "payload": {
            "headers": [
                {"name": "From", "value": "no-reply@vcbonline.com.vn"},
                {"name": "Subject", "value": "Thong bao giao dich"},
                {"name": "Date", "value": "Wed, 22 Apr 2026 12:30:00 +0700"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        },
    }
    raw = raw_email_from_gmail(msg)
    assert raw.from_addr == "no-reply@vcbonline.com.vn"
    assert "Pho bo" in raw.body_text
    assert raw.received_at is not None


def test_forwarded_detection_without_fwd_prefix():
    """Forwarded email with no 'Fwd:' prefix — detected by body marker."""
    import base64

    body = (
        "---------- Forwarded message ---------\n"
        "Từ: Timo Support <support@timo.vn>\n"
        "Date: Thứ 3, 22 Apr 2026 10:00\n"
        "Subject: Thông báo thay đổi số dư tài khoản\n"
        "To: me@example.com\n\n"
        "Tài khoản Spend Account vừa giảm 120.000 VND vào 22/04/2026 10:00."
    )
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    msg = {
        "id": "no-fwd-prefix",
        "payload": {
            "headers": [
                {"name": "From", "value": "Me <me.other@gmail.com>"},
                {"name": "Subject", "value": "Thông báo thay đổi số dư tài khoản"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        },
    }
    raw = raw_email_from_gmail(msg)
    # Marker detected → sender overridden
    assert raw.from_addr == "support@timo.vn"
    parsed = parse_email(raw)
    assert parsed is not None
    assert parsed.rule_name == "Timo"
    assert parsed.kind == "expense"


def test_non_forwarded_keeps_outer_sender():
    """Regular email without forwarded marker keeps its outer sender."""
    import base64

    body = "Hi,\n\nReach us at contact@ourcompany.com for queries.\nRegards"
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    msg = {
        "id": "regular",
        "payload": {
            "headers": [
                {"name": "From", "value": "newsletter@example.com"},
                {"name": "Subject", "value": "Monthly newsletter"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        },
    }
    raw = raw_email_from_gmail(msg)
    # No marker and no From: header in body → keep outer sender.
    assert raw.from_addr == "newsletter@example.com"


def test_looks_forwarded_signals():
    from money_api.ingest.gmail_parser import looks_forwarded

    assert looks_forwarded("Fwd: abc", "")
    assert looks_forwarded("FW: xyz", "")
    assert looks_forwarded("Trs: abc", "")  # French variant
    assert looks_forwarded("abc", "---------- Forwarded message ---------\n")
    assert looks_forwarded(
        "abc",
        "Begin forwarded message:\nFrom: x@y.com\n",
    )
    assert looks_forwarded("abc", "From: foo@bar.com\nDate: ...")  # header block
    assert not looks_forwarded("Hello", "No forwarding markers here at all")


def test_raw_email_handles_html():
    import base64

    html = b"<html><body><p>So tien: -100.000 VND</p><p>Noi dung: Coffee</p></body></html>"
    encoded = base64.urlsafe_b64encode(html).decode().rstrip("=")
    msg = {
        "id": "abc",
        "payload": {
            "headers": [
                {"name": "From", "value": "no-reply@vcbonline.com.vn"},
                {"name": "Subject", "value": "giao dich"},
            ],
            "mimeType": "text/html",
            "body": {"data": encoded},
        },
    }
    raw = raw_email_from_gmail(msg)
    assert "100.000" in raw.body_text
    assert "<p>" not in raw.body_text


def test_raw_email_uses_internal_date_when_header_missing():
    """Some bank senders omit / malform the Date header. Gmail's internalDate
    (ms since epoch) is the reliable fallback for received_at."""
    import base64
    from datetime import datetime, timezone as _tz

    body = base64.urlsafe_b64encode(b"Test body").decode().rstrip("=")
    utc_moment = datetime(2026, 4, 23, 14, 23, 45, tzinfo=_tz.utc)
    msg = {
        "id": "abc",
        "internalDate": str(int(utc_moment.timestamp() * 1000)),
        "payload": {
            "headers": [
                {"name": "From", "value": "bank@example.com"},
                {"name": "Subject", "value": "giao dich"},
                # NO Date header
            ],
            "mimeType": "text/plain",
            "body": {"data": body},
        },
    }
    raw = raw_email_from_gmail(msg)
    assert raw.received_at is not None
    # Key property: the fallback produces a clock time (not 00:00:00 midnight)
    assert (raw.received_at.hour, raw.received_at.minute) != (0, 0)
    # Within ±24h of the fixture moment after tz conversion
    assert (
        abs(
            (raw.received_at - utc_moment.replace(tzinfo=None)).total_seconds()
        )
        < 24 * 3600
    )


def test_raw_email_uses_internal_date_when_header_malformed():
    """Malformed Date header (e.g. non-RFC-2822) should fall back to internalDate."""
    import base64

    body = base64.urlsafe_b64encode(b"Test").decode().rstrip("=")
    msg = {
        "id": "abc2",
        "internalDate": "1777163025000",
        "payload": {
            "headers": [
                {"name": "From", "value": "bank@example.com"},
                {"name": "Subject", "value": "giao dich"},
                {"name": "Date", "value": "not-a-valid-date"},
            ],
            "mimeType": "text/plain",
            "body": {"data": body},
        },
    }
    raw = raw_email_from_gmail(msg)
    assert raw.received_at is not None


def test_rule_with_category_hint_populates_parsed_category():
    """Rules with a category_hint should fill ParsedTx.category so ingest can
    resolve to an id instead of leaving it NULL."""
    from money_api.ingest.gmail_parser import Rule, apply_rule

    rule = Rule(
        name="test-rule",
        sender_globs=["*@bank.example"],
        subject_any=["transfer"],
        account_hint="TestBank",
        amount_patterns=[r"([\d\.,]+)\s*VND"],
        category_hint="Chưa phân loại",
    )
    email = RawEmail(
        message_id="t1",
        from_addr="notify@bank.example",
        subject="transfer notification",
        body_text="You spent 50,000 VND.",
    )
    parsed = apply_rule(rule, email)
    assert parsed is not None
    assert parsed.category == "Chưa phân loại"


def test_builtin_rules_have_category_hints():
    """HSBC + Timo + VCB-credit-card rules should all carry a category_hint so
    rule-hit ingestion doesn't leave category NULL."""
    from money_api.ingest.gmail_parser import BUILTIN_RULES

    wanted = {"VCB-credit-card", "Timo", "HSBC-credit-card"}
    for r in BUILTIN_RULES:
        if r.name in wanted:
            assert r.category_hint is not None, (
                f"rule '{r.name}' should have a category_hint"
            )
