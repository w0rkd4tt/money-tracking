"""Passkey router integration tests.

Only covers the plumbing around the WebAuthn ceremonies — auth gates, rate
limiting, validation, list/delete. A full round-trip requires a real
authenticator's private key (Touch ID / Face ID / security key) and is
verified manually in the browser.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_passkey_state():
    """Challenge store is module-level in-memory; rate limiter is in
    ui_unlock. Reset both between tests."""
    from money_api.services import ui_passkey, ui_unlock

    ui_passkey._pending.clear()
    ui_unlock._attempts.clear()
    yield
    ui_passkey._pending.clear()
    ui_unlock._attempts.clear()


@pytest.mark.asyncio
async def test_status_initially_has_zero_passkeys(client):
    r = await client.get("/api/v1/ui/status")
    assert r.status_code == 200
    assert r.json()["passkey_count"] == 0


@pytest.mark.asyncio
async def test_register_begin_requires_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.post("/api/v1/ui/passkey/register/begin")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_begin_returns_options_when_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    # Cookie from setup still active
    r = await client.post("/api/v1/ui/passkey/register/begin")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "state_id" in body
    opts = body["options"]
    # WebAuthn spec fields the browser needs
    assert "challenge" in opts
    assert "rp" in opts and opts["rp"]["id"] == "localhost"
    assert "user" in opts
    assert "pubKeyCredParams" in opts


@pytest.mark.asyncio
async def test_register_finish_requires_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.post(
        "/api/v1/ui/passkey/register/finish",
        json={"state_id": "xxx", "response": {}, "name": "TestDevice"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_finish_rejects_unknown_state(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    r = await client.post(
        "/api/v1/ui/passkey/register/finish",
        json={
            "state_id": "nonexistent",
            "response": {"id": "x", "rawId": "x", "response": {}, "type": "public-key"},
            "name": "TestDevice",
        },
    )
    assert r.status_code == 400
    assert "expired or unknown" in r.text


@pytest.mark.asyncio
async def test_auth_begin_409_when_no_passkeys(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.post("/api/v1/ui/passkey/auth/begin")
    assert r.status_code == 409
    assert "no passkeys" in r.text


@pytest.mark.asyncio
async def test_auth_finish_unknown_state(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.post(
        "/api/v1/ui/passkey/auth/finish",
        json={"state_id": "nonexistent", "response": {"id": "x"}},
    )
    assert r.status_code == 401
    assert "verification failed" in r.text


@pytest.mark.asyncio
async def test_list_requires_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.get("/api/v1/ui/passkey")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_empty_when_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    r = await client.get("/api/v1/ui/passkey")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_delete_requires_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.delete("/api/v1/ui/passkey/1")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_404_when_missing(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    r = await client.delete("/api/v1/ui/passkey/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_status_passkey_count_reflects_inserts(client):
    """Insert a passkey row directly (bypass WebAuthn crypto) and confirm
    /status surfaces the count so the unlock page can show the passkey button."""
    from money_api.db import SessionLocal
    from money_api.models import UiPasskey

    await client.post("/api/v1/ui/setup", json={"pin": "123456"})

    async with SessionLocal() as db:
        db.add(
            UiPasskey(
                credential_id=b"\x01" * 32,
                public_key=b"\x02" * 64,
                sign_count=0,
                name="Stub",
                transports="internal",
            )
        )
        await db.commit()

    r = await client.get("/api/v1/ui/status")
    assert r.status_code == 200
    assert r.json()["passkey_count"] == 1


@pytest.mark.asyncio
async def test_delete_removes_row(client):
    from money_api.db import SessionLocal
    from money_api.models import UiPasskey

    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    async with SessionLocal() as db:
        pk = UiPasskey(
            credential_id=b"\x03" * 32,
            public_key=b"\x04" * 64,
            sign_count=0,
            name="DeleteMe",
        )
        db.add(pk)
        await db.commit()
        await db.refresh(pk)
        pk_id = pk.id

    r = await client.delete(f"/api/v1/ui/passkey/{pk_id}")
    assert r.status_code == 204

    r = await client.get("/api/v1/ui/passkey")
    assert r.status_code == 200
    assert r.json() == []
