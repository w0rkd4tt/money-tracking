import pytest


@pytest.fixture(autouse=True)
def _reset_ui_rate_limiter():
    """Rate limiter is module-level in-memory dict; reset between tests so
    earlier-failing-on-purpose tests don't poison later ones."""
    from money_api.services import ui_unlock

    ui_unlock._attempts.clear()
    yield
    ui_unlock._attempts.clear()


@pytest.mark.asyncio
async def test_status_not_configured(client):
    r = await client.get("/api/v1/ui/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["unlocked"] is False


@pytest.mark.asyncio
async def test_setup_then_status_unlocked(client):
    r = await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    assert r.status_code == 201, r.text
    body = r.json()
    # Recovery key: 20-byte base32 → 32 chars → 8 groups of 4, 7 hyphens
    rk = body["recovery_key"]
    assert rk.count("-") == 7
    assert all(len(g) == 4 for g in rk.split("-"))

    # Cookie was set → status shows unlocked
    r = await client.get("/api/v1/ui/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["unlocked"] is True


@pytest.mark.asyncio
async def test_duplicate_setup_rejected(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    r = await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_unlock_wrong_pin(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    # Simulate a fresh browser — clear cookies
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"pin": "999999"})
    assert r.status_code == 401
    # Status still configured but not unlocked
    s = await client.get("/api/v1/ui/status")
    body = s.json()
    assert body["configured"] is True
    assert body["unlocked"] is False


@pytest.mark.asyncio
async def test_unlock_correct(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"pin": "123456"})
    assert r.status_code == 200
    assert "mt_session" in r.cookies or "mt_session" in client.cookies
    s = await client.get("/api/v1/ui/status")
    assert s.json()["unlocked"] is True


@pytest.mark.asyncio
async def test_logout(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    r = await client.post("/api/v1/ui/logout")
    assert r.status_code == 204
    s = await client.get("/api/v1/ui/status")
    body = s.json()
    assert body["configured"] is True
    assert body["unlocked"] is False


@pytest.mark.asyncio
async def test_rate_limit_after_failures(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    # 5 failures → 6th should be 429
    for _ in range(5):
        r = await client.post("/api/v1/ui/unlock", json={"pin": "000000"})
        assert r.status_code == 401
    r = await client.post("/api/v1/ui/unlock", json={"pin": "000000"})
    assert r.status_code == 429
    # Even correct PIN is blocked during window
    r = await client.post("/api/v1/ui/unlock", json={"pin": "123456"})
    assert r.status_code == 429
    # Reset limiter state for subsequent tests
    from money_api.services.ui_unlock import reset_attempts

    reset_attempts("unknown")
    reset_attempts("testclient")


@pytest.mark.asyncio
async def test_change_pin(client):
    setup_resp = (
        await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    ).json()
    old_recovery = setup_resp["recovery_key"]
    r = await client.post(
        "/api/v1/ui/change-pin",
        json={"old_pin": "123456", "new_pin": "654321"},
    )
    assert r.status_code == 200, r.text
    new_recovery = r.json()["new_recovery_key"]
    assert new_recovery != old_recovery
    # New PIN works
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"pin": "654321"})
    assert r.status_code == 200
    # Old PIN doesn't
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"pin": "123456"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_pin_requires_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()  # logged out
    r = await client.post(
        "/api/v1/ui/change-pin",
        json={"old_pin": "123456", "new_pin": "654321"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_recover_flow(client):
    setup_resp = (
        await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    ).json()
    recovery_key = setup_resp["recovery_key"]
    client.cookies.clear()
    # Recover with the printed key (with hyphens) — test case-insensitive + hyphens
    r = await client.post(
        "/api/v1/ui/recover",
        json={"recovery_key": recovery_key.lower(), "new_pin": "222333"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_recovery_key"] != recovery_key
    # New PIN works
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"pin": "222333"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_recover_wrong_key(client):
    await client.post("/api/v1/ui/setup", json={"pin": "123456"})
    client.cookies.clear()
    r = await client.post(
        "/api/v1/ui/recover",
        json={"recovery_key": "WRONG-KEY-HERE-0000", "new_pin": "222333"},
    )
    assert r.status_code == 401
    from money_api.services.ui_unlock import reset_attempts

    reset_attempts("testclient")


@pytest.mark.asyncio
async def test_setup_rejects_non_numeric_pin(client):
    r = await client.post("/api/v1/ui/setup", json={"pin": "abcdef"})
    assert r.status_code == 422  # Pydantic pattern


@pytest.mark.asyncio
async def test_setup_rejects_wrong_length_pin(client):
    r = await client.post("/api/v1/ui/setup", json={"pin": "12345"})
    assert r.status_code == 422
    r = await client.post("/api/v1/ui/setup", json={"pin": "1234567"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_api_endpoints_remain_open(client):
    """API data routes are NOT gated — UI unlock is UI-only."""
    # Without any unlock/setup, accounts list should still respond (200, empty list).
    r = await client.get("/api/v1/accounts")
    assert r.status_code == 200
    # And we can create one without a session cookie.
    client.cookies.clear()
    r = await client.post(
        "/api/v1/accounts",
        json={"name": "NoAuth", "type": "cash", "currency": "VND"},
    )
    assert r.status_code == 201
