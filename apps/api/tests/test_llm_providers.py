"""Tests for LLM provider feature: encryption at rest + SSRF guard + timeout."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_api_key_encrypted_at_rest(client):
    """After POST, raw DB row stores ciphertext bytes, not the plaintext key."""
    secret = "sk-test-super-secret-12345"
    r = await client.post(
        "/api/v1/llm/providers",
        json={
            "name": "test_enc",
            "endpoint": "https://8.8.8.8/chat",
            "model": "gpt-x",
            "api_key": secret,
            "timeout_sec": 30,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Response never contains the plaintext api_key (only has_api_key bool).
    assert "api_key" not in body
    assert body["has_api_key"] is True

    # Inspect the DB row directly to confirm it's not plaintext.
    from money_api.db import engine

    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT api_key FROM llm_provider WHERE name = 'test_enc'"))
        ).first()
    stored = row.api_key
    assert stored is not None
    # Ciphertext must NOT equal plaintext bytes.
    assert stored != secret.encode()
    assert secret.encode() not in bytes(stored)

    # But the ORM read path decrypts transparently.
    from money_api.models import LlmProvider
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select as _sel

    async with AsyncSession(engine) as s:
        fetched = (
            await s.execute(_sel(LlmProvider).where(LlmProvider.name == "test_enc"))
        ).scalar_one()
    assert fetched.api_key == secret


@pytest.mark.asyncio
async def test_api_key_null_preserved(client):
    """Creating without api_key stores NULL (not encrypted empty string)."""
    r = await client.post(
        "/api/v1/llm/providers",
        json={
            "name": "no_key",
            "endpoint": "https://8.8.8.8/chat",
            "model": "gpt-x",
        },
    )
    assert r.status_code == 200
    assert r.json()["has_api_key"] is False

    from money_api.db import engine

    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT api_key FROM llm_provider WHERE name = 'no_key'"))
        ).first()
    assert row.api_key is None


@pytest.mark.asyncio
async def test_ssrf_guard_blocks_private_on_create(client):
    """POST with a private-IP endpoint is rejected with 403."""
    cases = [
        "http://192.168.1.1:8080/chat",
        "http://10.0.0.1/chat",
        "http://172.16.0.1/chat",
        "http://169.254.169.254/latest/meta-data",  # AWS metadata
    ]
    for url in cases:
        r = await client.post(
            "/api/v1/llm/providers",
            json={
                "name": f"bad_{url}",
                "endpoint": url,
                "model": "x",
            },
        )
        assert r.status_code == 403, f"{url} should be blocked: {r.text}"
        assert "SSRF" in r.text


@pytest.mark.asyncio
async def test_ssrf_guard_blocks_bad_scheme(client):
    r = await client.post(
        "/api/v1/llm/providers",
        json={"name": "bad_scheme", "endpoint": "file:///etc/passwd", "model": "x"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ssrf_guard_allows_public(client):
    """Public HTTPS endpoint passes (we don't probe it, just validate URL)."""
    r = await client.post(
        "/api/v1/llm/providers",
        json={
            "name": "public_ok",
            "endpoint": "https://1.1.1.1/v1/chat/completions",
            "model": "gpt-4",
        },
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_ssrf_guard_allows_named_localhost(client):
    """localhost / host.docker.internal pass (dev convenience)."""
    for url in [
        "http://localhost:11434/api/chat",
        "http://host.docker.internal:11434/api/chat",
    ]:
        r = await client.post(
            "/api/v1/llm/providers",
            json={
                "name": f"local_{url.split('/')[2].split(':')[0]}",
                "endpoint": url,
                "model": "x",
            },
        )
        assert r.status_code == 200, f"{url} should pass: {r.text}"


@pytest.mark.asyncio
async def test_ssrf_guard_on_adhoc_test(client):
    """POST /test with a private endpoint returns 403 before opening a socket."""
    r = await client.post(
        "/api/v1/llm/providers/test",
        json={
            "endpoint": "http://127.0.0.1:5432/",
            "model": "x",
            "timeout_sec": 3,
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ssrf_guard_on_patch(client):
    """PATCH endpoint is also validated (can't repoint to private IP later)."""
    create = await client.post(
        "/api/v1/llm/providers",
        json={"name": "p1", "endpoint": "https://8.8.8.8", "model": "x"},
    )
    assert create.status_code == 200
    pid = int(create.json()["id"].split(":")[1])
    r = await client.patch(
        f"/api/v1/llm/providers/{pid}",
        json={"endpoint": "http://192.168.1.1/chat"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ping_timeout_honored_on_adhoc(client, monkeypatch):
    """ping_with_detail receives timeout_override from adhoc test request."""
    captured = {}
    from money_api.llm import provider as prov_mod

    original = prov_mod.OllamaProvider.ping_with_detail

    async def fake_ping(self, timeout_override=None):
        captured["timeout"] = timeout_override
        return True, "reachable"

    monkeypatch.setattr(prov_mod.OllamaProvider, "ping_with_detail", fake_ping)

    r = await client.post(
        "/api/v1/llm/providers/test",
        json={
            "endpoint": "https://1.1.1.1/v1/chat/completions",
            "model": "gpt-4",
            "timeout_sec": 7,
        },
    )
    assert r.status_code == 200
    assert captured["timeout"] == 7.0

    # Restore
    monkeypatch.setattr(prov_mod.OllamaProvider, "ping_with_detail", original)


@pytest.mark.asyncio
async def test_ping_timeout_caps_stored_provider(monkeypatch):
    """Stored provider with timeout=120 should cap at 30 for ping."""
    from money_api.llm.provider import OllamaProvider

    captured_timeout = {}

    class FakeClient:
        def __init__(self, *, timeout):
            captured_timeout["val"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            class R:
                status_code = 200

            return R()

        async def post(self, *args, **kwargs):
            class R:
                status_code = 200

                def raise_for_status(self):
                    pass

            return R()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    provider = OllamaProvider(
        name="slow", url="https://example.com", model="x", timeout=120
    )
    ok, _ = await provider.ping_with_detail()
    assert ok
    assert captured_timeout["val"] == 30  # capped

    ok, _ = await provider.ping_with_detail(timeout_override=5)
    assert captured_timeout["val"] == 5


# ---------------------------------------------------------------------------
# Response-shape parsing: Ollama vs OpenAI vs Anthropic
# ---------------------------------------------------------------------------


def test_extract_content_ollama_shape():
    from money_api.llm.provider import _extract_content

    assert (
        _extract_content({"message": {"content": '{"a": 1}'}}) == '{"a": 1}'
    )


def test_extract_content_openai_shape():
    from money_api.llm.provider import _extract_content

    data = {"choices": [{"message": {"content": '{"a": 2}'}}]}
    assert _extract_content(data) == '{"a": 2}'


def test_extract_content_openai_text_shape():
    from money_api.llm.provider import _extract_content

    # Older completion endpoint may use `text` on choice
    assert _extract_content({"choices": [{"text": "plain"}]}) == "plain"


def test_extract_content_anthropic_shape():
    from money_api.llm.provider import _extract_content

    data = {
        "content": [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ]
    }
    assert _extract_content(data) == "hello world"


def test_extract_content_empty_fallback():
    from money_api.llm.provider import _extract_content

    assert _extract_content({}) == ""
    assert _extract_content({"choices": []}) == ""
    assert _extract_content(None) == ""


@pytest.mark.asyncio
async def test_chat_parses_openai_shape(monkeypatch):
    """Full chat() with a mocked httpx returning OpenAI-style JSON parses correctly."""
    from money_api.llm.provider import OllamaProvider

    class FakeClient:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            class R:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"transactions":[{"amount":30000}]}'
                                }
                            }
                        ]
                    }

            return R()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    provider = OllamaProvider(
        name="openai_like", url="https://api.example.com", model="x", timeout=30
    )
    result = await provider.chat([{"role": "user", "content": "t"}], schema={"type": "object"})
    assert result == {"transactions": [{"amount": 30000}]}
