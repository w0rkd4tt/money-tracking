"""Regression tests for the /categories router dedup guard."""

import pytest


@pytest.mark.asyncio
async def test_create_rejects_duplicate_same_parent_and_kind(client):
    """Creating the same (name, kind, parent_id) twice returns 409. Stops the
    'user clicks + Tạo twice' bug that produced 7 identical Ăn uống rows and
    broke LLM category resolution."""
    first = await client.post(
        "/api/v1/categories",
        json={"name": "Cà phê", "kind": "expense"},
    )
    assert first.status_code == 201, first.text

    dup = await client.post(
        "/api/v1/categories",
        json={"name": "Cà phê", "kind": "expense"},
    )
    assert dup.status_code == 409
    assert "already exists" in dup.text


@pytest.mark.asyncio
async def test_create_allows_same_name_different_parent(client):
    """Same leaf name under a different parent is a different category, not a
    duplicate — two 'Online' children under 'Mua sắm' and 'Giải trí' are OK."""
    shopping = await client.post(
        "/api/v1/categories", json={"name": "Mua sắm", "kind": "expense"}
    )
    entertainment = await client.post(
        "/api/v1/categories", json={"name": "Giải trí", "kind": "expense"}
    )
    sid = shopping.json()["id"]
    eid = entertainment.json()["id"]

    a = await client.post(
        "/api/v1/categories",
        json={"name": "Online", "kind": "expense", "parent_id": sid},
    )
    b = await client.post(
        "/api/v1/categories",
        json={"name": "Online", "kind": "expense", "parent_id": eid},
    )
    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text


@pytest.mark.asyncio
async def test_create_allows_same_name_different_kind(client):
    """'Hoàn tiền' can exist as both income (rebate) and expense (partial
    refund back to card). Kind differentiates them so both are allowed."""
    a = await client.post(
        "/api/v1/categories", json={"name": "Hoàn tiền", "kind": "income"}
    )
    b = await client.post(
        "/api/v1/categories", json={"name": "Hoàn tiền", "kind": "expense"}
    )
    assert a.status_code == 201
    assert b.status_code == 201


@pytest.mark.asyncio
async def test_create_strips_whitespace_before_dedup(client):
    """'Ăn uống' and '  Ăn uống  ' collide — leading/trailing whitespace is
    normalised before the dedup check to stop trivial bypasses."""
    a = await client.post(
        "/api/v1/categories", json={"name": "Ăn uống", "kind": "expense"}
    )
    assert a.status_code == 201
    b = await client.post(
        "/api/v1/categories", json={"name": "  Ăn uống  ", "kind": "expense"}
    )
    assert b.status_code == 409
