import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_TMP = Path(tempfile.mkdtemp(prefix="moneytrack_test_"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["APP_ENCRYPTION_KEY"] = "test-key-insecure"
os.environ["M1ULTRA_URL"] = "http://127.0.0.1:1"


@pytest_asyncio.fixture(scope="function")
async def app_engine():
    # Reset settings cache in case previous tests mutated env.
    from money_api.config import get_settings

    get_settings.cache_clear()
    # Import models so their tables register on Base.metadata before create_all.
    from money_api import models  # noqa: F401
    from money_api.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine


@pytest_asyncio.fixture
async def client(app_engine) -> AsyncGenerator[AsyncClient, None]:
    from money_api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seeded(client):
    """Minimal fixture: 2 accounts, 3 categories."""
    await client.post(
        "/api/v1/accounts",
        json={"name": "Tiền mặt", "type": "cash", "currency": "VND", "is_default": True},
    )
    await client.post(
        "/api/v1/accounts",
        json={"name": "VCB", "type": "bank", "currency": "VND"},
    )
    await client.post("/api/v1/categories", json={"name": "Ăn uống", "kind": "expense"})
    await client.post("/api/v1/categories", json={"name": "Lương", "kind": "income"})
    await client.post("/api/v1/categories", json={"name": "Transfer", "kind": "transfer"})
    return client


@pytest.fixture
def anyio_backend():
    return "asyncio"
