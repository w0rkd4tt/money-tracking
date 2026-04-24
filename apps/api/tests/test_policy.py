import pytest


@pytest.mark.asyncio
async def test_policy_deny_by_default(client):
    r = await client.post("/api/v1/llm/policies/gmail/test", json={"query": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is False
    assert "denied" in body["reason"].lower()


@pytest.mark.asyncio
async def test_policy_allow_after_adding(client):
    await client.post(
        "/api/v1/llm/policies/gmail",
        json={
            "action": "allow",
            "pattern_type": "from",
            "pattern": "*@vcbonline.com.vn",
            "priority": 100,
            "enabled": True,
        },
    )
    await client.post(
        "/api/v1/llm/policies/gmail",
        json={
            "action": "deny",
            "pattern_type": "subject",
            "pattern": "OTP",
            "priority": 1000,
            "enabled": True,
        },
    )
    r = await client.post(
        "/api/v1/llm/policies/gmail/test",
        json={"query": "from:shopee"},
    )
    body = r.json()
    assert body["allowed"] is True
    assert "vcbonline" in body["rewritten_query"]
    assert "-subject:OTP" in body["rewritten_query"]


@pytest.mark.asyncio
async def test_redact():
    from money_api.llm.redact import redact

    text = "Card 4111 1111 1111 1234 — Số dư: 12.345.678 — OTP: 123456 for verification"
    out = redact(text)
    assert "1234" in out  # last 4 preserved
    assert "****" in out
    assert "[REDACTED]" in out
