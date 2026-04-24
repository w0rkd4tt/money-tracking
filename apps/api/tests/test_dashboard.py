from datetime import date

import pytest


@pytest.mark.asyncio
async def test_period_range_helper():
    from money_api.services.dashboard import period_range

    today = date(2026, 4, 22)  # Wednesday
    s, e, b = period_range("week", today)
    assert b == "day"
    assert s.strftime("%A") == "Monday"
    assert (e - s).days == 7

    s, e, b = period_range("month", today)
    assert b == "day"
    assert s == s.__class__(2026, 4, 1)
    assert e == e.__class__(2026, 5, 1)

    s, e, b = period_range("year", today)
    assert b == "month"
    assert s == s.__class__(2026, 1, 1)
    assert e == e.__class__(2027, 1, 1)


@pytest.mark.asyncio
async def test_overview_year_has_12_months(seeded):
    c = seeded
    r = await c.get("/api/v1/dashboard/overview?period=year")
    assert r.status_code == 200
    data = r.json()
    assert len(data["cashflow"]) == 12
    # First point = January 1
    first = data["cashflow"][0]["day"]
    assert first.endswith("-01-01")


@pytest.mark.asyncio
async def test_overview_week_has_7_days(seeded):
    c = seeded
    r = await c.get("/api/v1/dashboard/overview?period=week")
    assert r.status_code == 200
    data = r.json()
    assert len(data["cashflow"]) == 7


@pytest.mark.asyncio
async def test_category_stats_endpoint(seeded):
    c = seeded
    accts = (await c.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")
    cats = (await c.get("/api/v1/categories")).json()
    food_id = next(x["id"] for x in cats if x["name"] == "Ăn uống")

    for amount in ("-50000", "-120000", "-30000"):
        await c.post(
            "/api/v1/transactions",
            json={
                "ts": "2026-04-22T12:00:00",
                "amount": amount,
                "account_id": cash_id,
                "category_id": food_id,
                "source": "manual",
                "status": "confirmed",
            },
        )

    r = await c.get(f"/api/v1/categories/{food_id}/stats?period=month")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["category"]["name"] == "Ăn uống"
    assert s["period"] == "month"
    assert int(float(s["total"])) == 200_000
    assert s["count"] == 3
    assert int(float(s["avg_per_tx"])) == 66_666  # 200k / 3
    assert len(s["cashflow"]) >= 28
    assert len(s["transactions"]) == 3


@pytest.mark.asyncio
async def test_category_stats_unknown_id(client):
    r = await client.get("/api/v1/categories/99999/stats?period=month")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_overview_pie_breakdown_for_period(seeded):
    c = seeded
    accts = (await c.get("/api/v1/accounts")).json()
    cash_id = next(a["id"] for a in accts if a["name"] == "Tiền mặt")
    cats = (await c.get("/api/v1/categories")).json()
    food_id = next(x["id"] for x in cats if x["name"] == "Ăn uống")

    # 3 confirmed expenses this week
    for amount in ("-50000", "-30000", "-120000"):
        await c.post(
            "/api/v1/transactions",
            json={
                "ts": "2026-04-22T12:00:00",
                "amount": amount,
                "account_id": cash_id,
                "category_id": food_id,
                "source": "manual",
                "status": "confirmed",
            },
        )

    r = await c.get("/api/v1/dashboard/overview?period=week")
    data = r.json()
    bk = data["breakdown"]
    assert len(bk) == 1
    assert bk[0]["category_name"] == "Ăn uống"
    assert int(float(bk[0]["total"])) == 200000
    assert bk[0]["count"] == 3
    assert abs(bk[0]["pct"] - 100.0) < 0.01

    # KPI label matches period
    labels = [k["label"] for k in data["kpis"]]
    assert any("tuần" in l.lower() for l in labels)
