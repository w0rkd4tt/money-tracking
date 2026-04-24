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
    r = await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    assert r.status_code == 201, r.text
    body = r.json()
    # Recovery key in format XXXX-XXXX-XXXX-XXXX-XXXX-XXXX (6 groups of 4)
    rk = body["recovery_key"]
    # 20-byte base32 → 32 chars → 8 groups of 4, 7 hyphens
    assert rk.count("-") == 7
    assert all(len(g) == 4 for g in rk.split("-"))

    # Cookie was set → status shows unlocked
    r = await client.get("/api/v1/ui/status")
    assert r.status_code == 200
    assert r.json() == {"configured": True, "unlocked": True}


@pytest.mark.asyncio
async def test_duplicate_setup_rejected(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    r = await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_unlock_wrong_passphrase(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    # Simulate a fresh browser — clear cookies
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "wrong-password"})
    assert r.status_code == 401
    # Status still configured but not unlocked
    s = await client.get("/api/v1/ui/status")
    assert s.json() == {"configured": True, "unlocked": False}


@pytest.mark.asyncio
async def test_unlock_correct(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "hunter2hunter2"})
    assert r.status_code == 200
    assert "mt_session" in r.cookies or "mt_session" in client.cookies
    s = await client.get("/api/v1/ui/status")
    assert s.json()["unlocked"] is True


@pytest.mark.asyncio
async def test_logout(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    r = await client.post("/api/v1/ui/logout")
    assert r.status_code == 204
    s = await client.get("/api/v1/ui/status")
    assert s.json() == {"configured": True, "unlocked": False}


@pytest.mark.asyncio
async def test_rate_limit_after_failures(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    client.cookies.clear()
    # 5 failures → 6th should be 429
    for _ in range(5):
        r = await client.post("/api/v1/ui/unlock", json={"passphrase": "bad"})
        assert r.status_code == 401
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "bad"})
    assert r.status_code == 429
    # Even correct passphrase is blocked during window
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "hunter2hunter2"})
    assert r.status_code == 429
    # Reset limiter state for subsequent tests
    from money_api.services.ui_unlock import reset_attempts

    reset_attempts("unknown")
    reset_attempts("testclient")


@pytest.mark.asyncio
async def test_change_passphrase(client):
    setup_resp = (
        await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    ).json()
    old_recovery = setup_resp["recovery_key"]
    r = await client.post(
        "/api/v1/ui/change-passphrase",
        json={"old_passphrase": "hunter2hunter2", "new_passphrase": "newnewnew123"},
    )
    assert r.status_code == 200, r.text
    new_recovery = r.json()["new_recovery_key"]
    assert new_recovery != old_recovery
    # New passphrase works
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "newnewnew123"})
    assert r.status_code == 200
    # Old passphrase doesn't
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "hunter2hunter2"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_passphrase_requires_unlocked(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    client.cookies.clear()  # logged out
    r = await client.post(
        "/api/v1/ui/change-passphrase",
        json={"old_passphrase": "hunter2hunter2", "new_passphrase": "newnewnew123"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_recover_flow(client):
    setup_resp = (
        await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    ).json()
    recovery_key = setup_resp["recovery_key"]
    client.cookies.clear()
    # Recover with the printed key (with hyphens) — test case-insensitive + hyphens
    r = await client.post(
        "/api/v1/ui/recover",
        json={"recovery_key": recovery_key.lower(), "new_passphrase": "recovered123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_recovery_key"] != recovery_key
    # New passphrase works
    client.cookies.clear()
    r = await client.post("/api/v1/ui/unlock", json={"passphrase": "recovered123"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_recover_wrong_key(client):
    await client.post("/api/v1/ui/setup", json={"passphrase": "hunter2hunter2"})
    client.cookies.clear()
    r = await client.post(
        "/api/v1/ui/recover",
        json={"recovery_key": "WRONG-KEY-HERE-0000", "new_passphrase": "x12345678"},
    )
    assert r.status_code == 401
    from money_api.services.ui_unlock import reset_attempts

    reset_attempts("testclient")


@pytest.mark.asyncio
async def test_setup_too_short_passphrase(client):
    r = await client.post("/api/v1/ui/setup", json={"passphrase": "abc"})
    assert r.status_code == 422  # Pydantic min_length


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
