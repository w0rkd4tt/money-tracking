"""LLM provider abstraction.

`m1ultra` is a named provider pointing at Ollama on the host. Interface is:
    await chat(messages, schema=...) -> dict
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import LlmProvider

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class LLMInvalidOutput(RuntimeError):
    pass


class LLMProviderNotFound(RuntimeError):
    pass


def _strip_markdown_fences(text: str) -> str:
    """Strip ```json ... ``` or ``` ... ``` wrappers some models emit despite JSON mode."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    # Remove first fence line (``` or ```json)
    first_nl = s.find("\n")
    if first_nl == -1:
        return s
    body = s[first_nl + 1 :]
    # Remove trailing fence
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


def _extract_content(data: Any) -> str:
    """Pull assistant text out of whichever response shape the upstream uses.

    Supports:
      - Ollama:              `{"message": {"content": "..."}}`
      - OpenAI-compatible:   `{"choices": [{"message": {"content": "..."}}]}`
        (galaxy_one, deepseek, openrouter, llamaedge, vLLM w/ openai router…)
      - Anthropic-messages:  `{"content": [{"type": "text", "text": "..."}]}`
    Falls back to "" so the caller can raise a clearer "no content" error.
    """
    if not isinstance(data, dict):
        return ""
    # Ollama shape
    msg = data.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str) and content:
            return content
    # OpenAI shape
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            m = first.get("message")
            if isinstance(m, dict):
                c = m.get("content")
                if isinstance(c, str) and c:
                    return c
            # Some completion endpoints use `text` instead of `message`.
            t = first.get("text")
            if isinstance(t, str) and t:
                return t
    # Anthropic shape
    content = data.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                txt = part.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        if parts:
            return "".join(parts)
    if isinstance(content, str):
        return content
    return ""


class OllamaProvider:
    name: str

    def __init__(
        self,
        name: str,
        url: str,
        model: str,
        timeout: int,
        chat_endpoint: str | None = None,
        ping_endpoint: str | None = None,
        api_key: str | None = None,
    ):
        self.name = name
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.chat_endpoint = chat_endpoint or f"{self.url}/api/chat"
        self.ping_endpoint = ping_endpoint
        self.api_key = api_key

    async def chat(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        temperature: float = 0.1,
        num_predict: int | None = 512,
        think: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # Thinking models (qwen3.5 family) emit a separate "thinking" field
            # with CoT. For JSON extract we don't need it — disable to save tokens
            # and ensure `content` is populated.
            "think": think,
            "options": {"temperature": temperature},
        }
        if num_predict is not None:
            payload["options"]["num_predict"] = num_predict
        if schema is not None:
            # Ollama: structured output via `format=<schema>`.
            payload["format"] = schema
            # OpenAI-compatible endpoints (galaxy_one, deepseek, openrouter):
            # force JSON via `response_format`. Ollama ignores this field.
            payload["response_format"] = {"type": "json_object"}

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.chat_endpoint, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"Ollama unavailable: {e}") from e

        content = _extract_content(data)
        if schema is not None:
            cleaned = _strip_markdown_fences(content)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                log.warning("LLM returned invalid JSON: %s | raw=%r", e, content[:500])
                raise LLMInvalidOutput(f"Invalid JSON: {e}") from e
        return {"content": content}

    async def ping_with_detail(
        self, timeout_override: float | None = None
    ) -> tuple[bool, str]:
        """Probe reachability. Uses `timeout_override` if provided, else caps the
        provider's own timeout at 30s so the UI's "Test" button doesn't hang for
        the full chat timeout (often 120s)."""
        effective_timeout = (
            timeout_override
            if timeout_override is not None
            else min(self.timeout, 30)
        )
        try:
            async with httpx.AsyncClient(timeout=effective_timeout) as client:
                headers: dict[str, str] = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                if self.ping_endpoint:
                    r = await client.get(self.ping_endpoint, headers=headers)
                    if r.status_code == 200:
                        return True, "reachable"
                    return False, f"http_{r.status_code}"
                # For chat endpoints, perform a minimal non-streaming POST and
                # fail on auth/permission errors via raise_for_status().
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 1},
                }
                r = await client.post(self.chat_endpoint, json=payload, headers=headers)
                r.raise_for_status()
                return True, "reachable"
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else "unknown"
            return False, f"http_{code}"
        except httpx.TimeoutException:
            return False, "timeout"
        except httpx.RequestError:
            return False, "request_error"
        except Exception:
            return False, "error"

    async def ping(self) -> bool:
        ok, _ = await self.ping_with_detail()
        return ok


def get_m1ultra() -> OllamaProvider:
    s = get_settings()
    return OllamaProvider(
        name="m1ultra",
        url=s.m1ultra_url,
        model=s.m1ultra_model,
        timeout=s.m1ultra_timeout,
        ping_endpoint=f"{s.m1ultra_url.rstrip('/')}/api/tags",
    )


def get_agent_provider() -> OllamaProvider:
    s = get_settings()
    return OllamaProvider(
        name="m1ultra_agent",
        url=s.m1ultra_url,
        model=s.m1ultra_agent_model,
        timeout=s.m1ultra_timeout,
        ping_endpoint=f"{s.m1ultra_url.rstrip('/')}/api/tags",
    )


def get_galaxy_one() -> OllamaProvider:
    s = get_settings()
    return OllamaProvider(
        name="galaxy_one",
        # Endpoint may be full path; keep URL for diagnostics only.
        url=s.galaxy_one_endpoint,
        model=s.galaxy_one_model,
        timeout=s.galaxy_one_timeout,
        chat_endpoint=s.galaxy_one_endpoint,
        api_key=s.galaxy_one_api_key,
    )


def get_default_provider() -> OllamaProvider:
    s = get_settings()
    provider = s.llm_default_provider.strip().lower()
    if provider == "galaxy_one":
        return get_galaxy_one()
    return get_m1ultra()


def _builtin_providers() -> dict[str, OllamaProvider]:
    return {
        "m1ultra": get_m1ultra(),
        "galaxy_one": get_galaxy_one(),
    }


def _provider_from_row(row: LlmProvider) -> OllamaProvider:
    return OllamaProvider(
        name=row.name,
        url=row.endpoint,
        model=row.model,
        timeout=row.timeout_sec,
        chat_endpoint=row.endpoint,
        api_key=row.api_key,
    )


async def resolve_provider(
    session: AsyncSession, preferred: str | None = None
) -> OllamaProvider:
    builtins = _builtin_providers()
    preferred_name = (preferred or "").strip().lower()
    if preferred_name:
        row = (
            await session.execute(
                select(LlmProvider).where(
                    LlmProvider.name == preferred_name, LlmProvider.enabled.is_(True)
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return _provider_from_row(row)
        if preferred_name in builtins:
            return builtins[preferred_name]
        raise LLMProviderNotFound(f"Provider '{preferred_name}' not found")

    custom_default = (
        await session.execute(
            select(LlmProvider)
            .where(LlmProvider.enabled.is_(True), LlmProvider.is_default.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if custom_default is not None:
        return _provider_from_row(custom_default)
    return get_default_provider()


async def list_all_provider_meta(session: AsyncSession) -> list[dict[str, Any]]:
    s = get_settings()
    default_name = s.llm_default_provider.strip().lower()
    custom_rows = list(
        (await session.execute(select(LlmProvider).order_by(LlmProvider.created_at.desc()))).scalars()
    )
    overridden_names = {row.name for row in custom_rows}
    out: list[dict[str, Any]] = []
    for name, provider in _builtin_providers().items():
        if name in overridden_names:
            continue
        out.append(
            {
                "id": f"builtin:{name}",
                "source": "builtin",
                "name": name,
                "endpoint": provider.chat_endpoint,
                "model": provider.model,
                "timeout_sec": provider.timeout,
                "enabled": True,
                "is_default": name == default_name,
                "has_api_key": bool(provider.api_key),
            }
        )

    for row in custom_rows:
        out.append(
            {
                "id": f"custom:{row.id}",
                "source": "custom",
                "name": row.name,
                "endpoint": row.endpoint,
                "model": row.model,
                "timeout_sec": row.timeout_sec,
                "enabled": row.enabled,
                "is_default": row.is_default,
                "has_api_key": bool(row.api_key),
            }
        )
    return out
