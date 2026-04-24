import pytest


@pytest.mark.asyncio
async def test_transfer_creates_two_transactions_and_does_not_skew_expense(seeded):
    client = seeded

    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")
    vcb_id = next(a["id"] for a in accts if a["name"] == "VCB")

    # Add opening income to VCB so we can withdraw from it
    cats = (await client.get("/api/v1/categories")).json()
    luong = next(c["id"] for c in cats if c["name"] == "Lương")
    await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-04-01T09:00:00",
            "amount": "5000000",
            "account_id": vcb_id,
            "category_id": luong,
            "source": "manual",
            "status": "confirmed",
        },
    )

    # Rút ATM 2tr, phí 1100 → VCB giảm (2M + 1100), tiền mặt tăng 2M
    r = await client.post(
        "/api/v1/transfers",
        json={
            "ts": "2026-04-22T10:00:00",
            "from_account_id": vcb_id,
            "to_account_id": cash_id,
            "amount": "2000000",
            "fee": "1100",
            "note": "Rút ATM",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data["transaction_ids"]) == 2

    balances = {b["name"]: b["balance"] for b in (await client.get("/api/v1/accounts/balance")).json()}
    assert balances["VCB"] == "2998900.00"
    assert balances["Tiền mặt"] == "2000000.00"

    # Dashboard: transfer KHÔNG được tính vào expense/income
    stats = (
        await client.get("/api/v1/transactions/stats?from=2026-04-01&to=2026-04-30")
    ).json()
    # only income = 5M, no expense from the transfer
    assert int(float(stats["total_expense"])) == 0
    assert int(float(stats["total_income"])) == 5_000_000


@pytest.mark.asyncio
async def test_transfer_rejects_same_account(seeded):
    client = seeded
    accts = (await client.get("/api/v1/accounts")).json()
    vcb_id = next(a["id"] for a in accts if a["name"] == "VCB")

    r = await client.post(
        "/api/v1/transfers",
        json={
            "ts": "2026-04-22T10:00:00",
            "from_account_id": vcb_id,
            "to_account_id": vcb_id,
            "amount": "100000",
        },
    )
    assert r.status_code == 400
