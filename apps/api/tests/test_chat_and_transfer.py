"""Tests for chat extract integration with the transfer service and for
the DELETE /transfers/{id} endpoint.

The chat path for kind=transfer must call create_transfer() and produce
a TransferGroup + two transactions with source=chat_web.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_chat_response_reports_selected_provider(seeded):
    """When the request specifies `provider=<x>`, the response body's
    `provider` field must echo it back — not fall back to a hardcoded default.
    """
    c = seeded
    fake = {"transactions": []}
    with patch(
        "money_api.llm.chat_service.extract_transactions",
        return_value=fake,
    ):
        r = await c.post(
            "/api/v1/chat/message",
            json={
                "channel": "web",
                "external_id": "prov-test",
                "text": "anything",
                "provider": "galaxy_one",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "galaxy_one", (
        f"expected provider 'galaxy_one', got {body['provider']!r}"
    )


@pytest.mark.asyncio
async def test_chat_response_reports_default_when_unspecified(seeded):
    """With no provider override, response reports the actual default (m1ultra
    per env), not a hardcoded fallback string."""
    c = seeded
    fake = {"transactions": []}
    with patch(
        "money_api.llm.chat_service.extract_transactions",
        return_value=fake,
    ):
        r = await c.post(
            "/api/v1/chat/message",
            json={"channel": "web", "external_id": "def-test", "text": "x"},
        )
    assert r.status_code == 200
    # With the test env's defaults, llm_default_provider is "m1ultra".
    assert r.json()["provider"] == "m1ultra"


@pytest.mark.asyncio
async def test_chat_unknown_provider_falls_back_to_default(seeded):
    """Caller requesting a nonexistent provider shouldn't 500. Backend falls
    back to default, and response reports what was actually used."""
    c = seeded
    fake = {"transactions": []}
    with patch(
        "money_api.llm.chat_service.extract_transactions",
        return_value=fake,
    ):
        r = await c.post(
            "/api/v1/chat/message",
            json={
                "channel": "web",
                "external_id": "bad-prov",
                "text": "x",
                "provider": "nonexistent_provider_xyz",
            },
        )
    assert r.status_code == 200
    assert r.json()["provider"] == "m1ultra"


@pytest.mark.asyncio
async def test_chat_transfer_creates_transfer_group(seeded):
    c = seeded

    # Mock the LLM extract to return a transfer extraction deterministically
    fake = {
        "transactions": [
            {
                "amount": 500000,
                "currency": "VND",
                "kind": "transfer",
                "account": "VCB",
                "to_account": "Tiền mặt",
                "category": "Transfer",
                "merchant": None,
                "ts": datetime.now().replace(microsecond=0).isoformat(),
                "note": "Rút ATM via chat",
                "confidence": 0.95,
            }
        ]
    }

    with patch(
        "money_api.llm.chat_service.extract_transactions",
        return_value=fake,
    ):
        r = await c.post(
            "/api/v1/chat/message",
            json={
                "channel": "web",
                "external_id": "chat-test",
                "text": "rút 500k từ VCB về Tiền mặt",
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["intent"] == "create_transfer"
    assert len(data["transactions"]) == 1
    item = data["transactions"][0]
    assert item["kind"] == "transfer"
    assert item["id"] is not None

    # Verify the transfer was persisted
    transfers = (await c.get("/api/v1/transfers")).json()
    assert len(transfers) == 1
    tg = transfers[0]
    assert tg["source"] == "chat_web"
    assert Decimal(tg["amount"]) == Decimal("500000")
    # Balance shifted correctly
    balances = {
        b["name"]: Decimal(b["balance"])
        for b in (await c.get("/api/v1/accounts/balance")).json()
    }
    assert balances["VCB"] == Decimal("-500000")
    assert balances["Tiền mặt"] == Decimal("500000")


@pytest.mark.asyncio
async def test_chat_transfer_ambiguous_to_account(seeded):
    c = seeded
    fake = {
        "transactions": [
            {
                "amount": 200000,
                "currency": "VND",
                "kind": "transfer",
                "account": "VCB",
                "to_account": "NonExistentWallet",
                "ts": datetime.now().isoformat(),
                "confidence": 0.9,
            }
        ]
    }
    with patch("money_api.llm.chat_service.extract_transactions", return_value=fake):
        r = await c.post(
            "/api/v1/chat/message",
            json={"channel": "web", "external_id": "chat-amb", "text": "whatever"},
        )
    data = r.json()
    # Should not persist anything
    assert (await c.get("/api/v1/transfers")).json() == []
    item = data["transactions"][0]
    assert "to_account" in item["ambiguous_fields"]


@pytest.mark.asyncio
async def test_delete_transfer_removes_children(seeded):
    c = seeded
    accts = (await c.get("/api/v1/accounts")).json()
    vcb = next(a["id"] for a in accts if a["name"] == "VCB")
    cash = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    r = await c.post(
        "/api/v1/transfers",
        json={
            "ts": "2026-04-22T10:00:00",
            "from_account_id": vcb,
            "to_account_id": cash,
            "amount": "300000",
            "fee": "0",
        },
    )
    tr = r.json()
    assert len(tr["transaction_ids"]) == 2

    # Both child transactions exist
    txs = (await c.get("/api/v1/transactions?size=100")).json()["items"]
    assert sum(1 for t in txs if t["transfer_group_id"] == tr["id"]) == 2

    # Delete the transfer
    r2 = await c.delete(f"/api/v1/transfers/{tr['id']}")
    assert r2.status_code == 204

    # Group gone
    transfers = (await c.get("/api/v1/transfers")).json()
    assert transfers == []
    # Child transactions gone
    txs = (await c.get("/api/v1/transactions?size=100")).json()["items"]
    assert not any(t["transfer_group_id"] == tr["id"] for t in txs)
