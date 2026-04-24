import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    # Ollama unreachable in tests (by design)
    assert body["llm"] in {"ok", "unreachable"}


@pytest.mark.asyncio
async def test_create_and_list_accounts(client):
    r = await client.post(
        "/api/v1/accounts",
        json={"name": "Tiền mặt", "type": "cash", "currency": "VND", "is_default": True},
    )
    assert r.status_code == 201, r.text
    acc = r.json()
    assert acc["name"] == "Tiền mặt"
    assert acc["is_default"] is True

    r = await client.get("/api/v1/accounts")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_default_flag_unique(client):
    await client.post(
        "/api/v1/accounts",
        json={"name": "A", "type": "cash", "currency": "VND", "is_default": True},
    )
    r = await client.post(
        "/api/v1/accounts",
        json={"name": "B", "type": "bank", "currency": "VND", "is_default": True},
    )
    assert r.status_code == 201
    all_accts = (await client.get("/api/v1/accounts")).json()
    defaults = [a for a in all_accts if a["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "B"


@pytest.mark.asyncio
async def test_update_account(client):
    r = await client.post(
        "/api/v1/accounts",
        json={"name": "Momo", "type": "ewallet", "currency": "VND"},
    )
    acc = r.json()
    r2 = await client.patch(
        f"/api/v1/accounts/{acc['id']}",
        json={"name": "Momo renamed", "color": "#ec4899", "opening_balance": "100000"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["name"] == "Momo renamed"
    assert body["color"] == "#ec4899"
    assert body["opening_balance"] == "100000.00"


@pytest.mark.asyncio
async def test_archive_and_unarchive(client):
    r = await client.post(
        "/api/v1/accounts",
        json={"name": "TempBank", "type": "bank", "currency": "VND"},
    )
    acc_id = r.json()["id"]
    # Archive (DELETE is soft)
    r2 = await client.delete(f"/api/v1/accounts/{acc_id}")
    assert r2.status_code == 204
    # Not in default list
    rows = (await client.get("/api/v1/accounts")).json()
    assert not any(a["id"] == acc_id for a in rows)
    # Visible with include_archived
    rows2 = (await client.get("/api/v1/accounts?include_archived=true")).json()
    assert any(a["id"] == acc_id and a["archived"] for a in rows2)
    # Unarchive via PATCH
    r3 = await client.patch(f"/api/v1/accounts/{acc_id}", json={"archived": False})
    assert r3.status_code == 200
    assert r3.json()["archived"] is False


@pytest.mark.asyncio
async def test_balance_reflects_transactions(seeded):
    client = seeded
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")
    food_id = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in food_id if c["name"] == "Ăn uống")

    r = await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-04-22T12:00:00",
            "amount": "-45000",
            "account_id": cash_id,
            "category_id": food_id,
            "source": "manual",
            "status": "confirmed",
        },
    )
    assert r.status_code == 201

    r = await client.get("/api/v1/accounts/balance")
    balances = {b["name"]: b["balance"] for b in r.json()}
    assert balances["Tiền mặt"] == "-45000.00"
