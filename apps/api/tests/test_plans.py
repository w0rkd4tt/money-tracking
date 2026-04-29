import pytest


@pytest.mark.asyncio
async def test_bucket_crud(seeded):
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in cats if c["name"] == "Ăn uống")

    r = await client.post(
        "/api/v1/buckets",
        json={"name": "Thiết yếu", "icon": "🏠", "color": "#16a34a", "category_ids": [food_id]},
    )
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["name"] == "Thiết yếu"
    assert b["category_ids"] == [food_id]

    # Duplicate name rejected
    r = await client.post("/api/v1/buckets", json={"name": "Thiết yếu"})
    assert r.status_code == 409

    # List excludes archived by default
    buckets = (await client.get("/api/v1/buckets")).json()
    assert any(x["name"] == "Thiết yếu" for x in buckets)

    # Update: rename + change categories
    r = await client.patch(
        f"/api/v1/buckets/{b['id']}",
        json={"name": "Thiết yếu mới", "category_ids": []},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Thiết yếu mới"
    assert r.json()["category_ids"] == []


@pytest.mark.asyncio
async def test_bucket_account_routing(seeded):
    """Account-level mapping wins over category mapping. A coffee paid on a
    credit card lands in the credit-debt bucket regardless of merchant."""
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in cats if c["name"] == "Ăn uống")
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    # Create a credit account — auto-link to "Trả nợ thẻ TD" only fires if
    # the bucket exists by that exact name, so we create it first.
    debt_b = (
        await client.post(
            "/api/v1/buckets",
            json={"name": "Trả nợ thẻ TD", "icon": "💳", "category_ids": []},
        )
    ).json()
    cc = (
        await client.post(
            "/api/v1/accounts",
            json={"name": "Visa", "type": "credit", "currency": "VND"},
        )
    ).json()

    # Auto-link should have happened on POST /accounts
    debt_b_after = (
        await client.get(f"/api/v1/buckets/{debt_b['id']}")
    ).json()
    assert cc["id"] in debt_b_after["account_ids"]

    # Build the regular Thiết yếu bucket with Ăn uống category
    food_b = (
        await client.post(
            "/api/v1/buckets",
            json={"name": "Thiết yếu", "category_ids": [food_id]},
        )
    ).json()

    # Plan: 10M expected, 5M to each bucket
    await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-04-01",
            "expected_income": "10000000",
            "strategy": "soft",
            "allocations": [
                {"bucket_id": food_b["id"], "method": "amount", "value": "5000000", "rollover": False},
                {"bucket_id": debt_b["id"], "method": "amount", "value": "5000000", "rollover": False},
            ],
        },
    )

    # Two coffees: 100k on cash → Thiết yếu, 200k on credit → Trả nợ thẻ TD
    for amount, account_id in [("-100000", cash_id), ("-200000", cc["id"])]:
        await client.post(
            "/api/v1/transactions",
            json={
                "ts": "2026-04-15T12:00:00",
                "amount": amount,
                "account_id": account_id,
                "category_id": food_id,
                "source": "manual",
                "status": "confirmed",
            },
        )

    summary = (await client.get("/api/v1/plans/2026-04/summary")).json()
    food_status = next(x for x in summary["buckets"] if x["bucket_name"] == "Thiết yếu")
    debt_status = next(x for x in summary["buckets"] if x["bucket_name"] == "Trả nợ thẻ TD")
    # Cash coffee → category routing → Thiết yếu
    assert food_status["spent"] == "100000.00"
    # Credit coffee → account routing → Trả nợ thẻ TD (NOT Thiết yếu)
    assert debt_status["spent"] == "200000.00"
    # No double counting — total spent equals sum of cash + credit
    assert summary["total_spent"] == "300000.00"


@pytest.mark.asyncio
async def test_bucket_rejects_non_expense_category(seeded):
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    salary_id = next(c["id"] for c in cats if c["name"] == "Lương")  # income kind
    r = await client.post(
        "/api/v1/buckets", json={"name": "B1", "category_ids": [salary_id]}
    )
    assert r.status_code == 400
    assert "expense" in r.text.lower()


@pytest.mark.asyncio
async def test_plan_create_and_summary(seeded):
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in cats if c["name"] == "Ăn uống")
    salary_id = next(c["id"] for c in cats if c["name"] == "Lương")
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    b = (
        await client.post(
            "/api/v1/buckets",
            json={"name": "Thiết yếu", "category_ids": [food_id]},
        )
    ).json()

    # Create plan for 2026-04 with 20M expected income, 10M for Thiết yếu
    r = await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-04-01",
            "expected_income": "20000000",
            "strategy": "soft",
            "allocations": [
                {
                    "bucket_id": b["id"],
                    "method": "amount",
                    "value": "10000000",
                    "rollover": True,
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["expected_income"] == "20000000.00"
    assert len(plan["allocations"]) == 1

    # Duplicate plan rejected
    r2 = await client.post(
        "/api/v1/plans", json={"month": "2026-04-01", "expected_income": "1"}
    )
    assert r2.status_code == 409

    # Add transactions: 3M spent on food, 20M salary income
    await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-04-10T12:00:00",
            "amount": "-3000000",
            "account_id": cash_id,
            "category_id": food_id,
            "source": "manual",
            "status": "confirmed",
        },
    )
    await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-04-01T09:00:00",
            "amount": "20000000",
            "account_id": cash_id,
            "category_id": salary_id,
            "source": "manual",
            "status": "confirmed",
        },
    )

    r = await client.get("/api/v1/plans/2026-04/summary")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["expected_income"] == "20000000.00"
    assert s["actual_income"] == "20000000.00"
    assert s["total_allocated"] == "10000000.00"
    assert s["total_spent"] == "3000000.00"
    assert s["unplanned_spent"] == "0.00"
    thiet_yeu = next(x for x in s["buckets"] if x["bucket_name"] == "Thiết yếu")
    assert thiet_yeu["allocated"] == "10000000.00"
    assert thiet_yeu["spent"] == "3000000.00"
    assert thiet_yeu["remaining"] == "7000000.00"
    assert thiet_yeu["status"] == "ok"
    assert 0 < thiet_yeu["pct"] < 50


@pytest.mark.asyncio
async def test_plan_percent_method(seeded):
    client = seeded
    b = (await client.post("/api/v1/buckets", json={"name": "Tiết kiệm"})).json()

    r = await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-05-01",
            "expected_income": "30000000",
            "allocations": [
                {"bucket_id": b["id"], "method": "percent", "value": "20", "rollover": False}
            ],
        },
    )
    assert r.status_code == 201, r.text
    s = (await client.get("/api/v1/plans/2026-05/summary")).json()
    saver = next(x for x in s["buckets"] if x["bucket_name"] == "Tiết kiệm")
    assert saver["allocated"] == "6000000.00"  # 30M × 20%


@pytest.mark.asyncio
async def test_plan_over_budget_status(seeded):
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in cats if c["name"] == "Ăn uống")
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    b = (
        await client.post(
            "/api/v1/buckets",
            json={"name": "Thiết yếu", "category_ids": [food_id]},
        )
    ).json()
    await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-06-01",
            "expected_income": "10000000",
            "allocations": [
                {"bucket_id": b["id"], "method": "amount", "value": "1000000"}
            ],
        },
    )
    # Spend 1.5M against a 1M allocation → over
    await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-06-05T12:00:00",
            "amount": "-1500000",
            "account_id": cash_id,
            "category_id": food_id,
            "source": "manual",
            "status": "confirmed",
        },
    )
    s = (await client.get("/api/v1/plans/2026-06/summary")).json()
    b_status = next(x for x in s["buckets"] if x["bucket_name"] == "Thiết yếu")
    assert b_status["status"] == "over"
    assert b_status["pct"] >= 100
    assert b_status["remaining"] == "-500000.00"


@pytest.mark.asyncio
async def test_plan_copy_from(seeded):
    client = seeded
    b = (await client.post("/api/v1/buckets", json={"name": "Thiết yếu"})).json()
    await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-07-01",
            "expected_income": "15000000",
            "note": "source",
            "allocations": [
                {"bucket_id": b["id"], "method": "amount", "value": "5000000"}
            ],
        },
    )
    r = await client.post("/api/v1/plans/2026-08/copy-from/2026-07")
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["month"] == "2026-08-01"
    assert plan["expected_income"] == "15000000.00"
    assert len(plan["allocations"]) == 1


@pytest.mark.asyncio
async def test_carry_over(seeded):
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in cats if c["name"] == "Ăn uống")
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    b = (
        await client.post(
            "/api/v1/buckets",
            json={"name": "Thiết yếu", "category_ids": [food_id]},
        )
    ).json()

    # Sep 2026: allocate 10M, spend 4M → dư 6M
    await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-09-01",
            "expected_income": "10000000",
            "allocations": [{"bucket_id": b["id"], "value": "10000000", "rollover": True}],
        },
    )
    await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-09-10T12:00:00",
            "amount": "-4000000",
            "account_id": cash_id,
            "category_id": food_id,
            "source": "manual",
            "status": "confirmed",
        },
    )

    # Oct 2026: allocate 10M, carry_over_enabled=True, rollover=True → effective = 16M
    await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-10-01",
            "expected_income": "10000000",
            "carry_over_enabled": True,
            "allocations": [{"bucket_id": b["id"], "value": "10000000", "rollover": True}],
        },
    )
    s = (await client.get("/api/v1/plans/2026-10/summary")).json()
    bucket = next(x for x in s["buckets"] if x["bucket_name"] == "Thiết yếu")
    assert bucket["allocated"] == "10000000.00"
    assert bucket["carry_in"] == "6000000.00"
    assert bucket["remaining"] == "16000000.00"  # 10M + 6M carry, 0 spent


@pytest.mark.asyncio
async def test_income_suggestion(seeded):
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    salary_id = next(c["id"] for c in cats if c["name"] == "Lương")
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    # 3 months of salary: 20M, 22M, 24M (avg = 22M)
    for month, amt in [("2026-01-15", "20000000"), ("2026-02-15", "22000000"), ("2026-03-15", "24000000")]:
        await client.post(
            "/api/v1/transactions",
            json={
                "ts": f"{month}T09:00:00",
                "amount": amt,
                "account_id": cash_id,
                "category_id": salary_id,
                "source": "manual",
                "status": "confirmed",
            },
        )

    r = await client.get("/api/v1/plans/suggest-income?month=2026-04")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "avg_3m"
    assert body["suggested"] == "22000000.00"


@pytest.mark.asyncio
async def test_unplanned_spend(seeded):
    """Tx in a category not mapped to any bucket → shows up as unplanned."""
    client = seeded
    cats = (await client.get("/api/v1/categories")).json()
    food_id = next(c["id"] for c in cats if c["name"] == "Ăn uống")
    accts = (await client.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")

    # Bucket exists but food NOT mapped
    b = (await client.post("/api/v1/buckets", json={"name": "Thiết yếu"})).json()
    await client.post(
        "/api/v1/plans",
        json={
            "month": "2026-11-01",
            "expected_income": "10000000",
            "allocations": [{"bucket_id": b["id"], "value": "5000000"}],
        },
    )
    await client.post(
        "/api/v1/transactions",
        json={
            "ts": "2026-11-05T12:00:00",
            "amount": "-500000",
            "account_id": cash_id,
            "category_id": food_id,
            "source": "manual",
            "status": "confirmed",
        },
    )
    s = (await client.get("/api/v1/plans/2026-11/summary")).json()
    assert s["unplanned_spent"] == "500000.00"
    assert s["total_spent"] == "500000.00"
