from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..llm.provider import (
    LLMProviderNotFound,
    OllamaProvider,
    list_all_provider_meta,
    resolve_provider,
)
from ..models import LlmProvider
from ..schemas.llm import (
    LlmProviderCreate,
    LlmProviderOut,
    LlmProviderTestRequest,
    LlmProviderTestResponse,
    LlmProviderUpdate,
)

router = APIRouter(prefix="/llm/providers", tags=["llm-providers"])

# Hostnames allowed to point at local services (dev convenience). Their resolved
# IP bypasses the private-IP block. Intentionally narrow: only the names users
# realistically use to reach Ollama on the host from inside Docker.
_ALLOWED_LOCAL_HOSTS = {"localhost", "host.docker.internal"}


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())


def _assert_endpoint_safe(url: str) -> None:
    """Block SSRF to private networks when the caller supplies a raw URL.

    Allows http/https only. Allows `localhost`/`host.docker.internal` by name (so
    user can probe the Ollama they already run on the host). Rejects any other
    hostname whose resolved IP falls in a loopback/private/link-local/reserved
    range.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid URL: {e}") from e

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL scheme must be http or https")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="URL host is required")

    if host in _ALLOWED_LOCAL_HOSTS:
        return

    # If the hostname is already a literal IP, parse directly. Otherwise resolve.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            resolved = socket.gethostbyname(host)
            ip = ipaddress.ip_address(resolved)
        except (socket.gaierror, ValueError) as e:
            raise HTTPException(
                status_code=400, detail=f"cannot resolve host '{host}': {e}"
            ) from e

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                f"endpoint blocked by SSRF guard: {ip} is in a "
                "reserved/private/loopback range"
            ),
        )


async def _get_custom_or_404(session: AsyncSession, provider_id: int) -> LlmProvider:
    row = (
        await session.execute(select(LlmProvider).where(LlmProvider.id == provider_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return row


@router.get("", response_model=list[LlmProviderOut])
async def list_providers(session: AsyncSession = Depends(get_session)):
    rows = await list_all_provider_meta(session)
    return [LlmProviderOut.model_validate(r) for r in rows]


@router.post("", response_model=LlmProviderOut)
async def create_provider(
    data: LlmProviderCreate, session: AsyncSession = Depends(get_session)
):
    _assert_endpoint_safe(data.endpoint.strip())
    name = _normalize_name(data.name)
    exists = (
        await session.execute(select(LlmProvider.id).where(LlmProvider.name == name))
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Provider name already exists")

    if data.is_default:
        for row in (await session.execute(select(LlmProvider))).scalars():
            row.is_default = False

    row = LlmProvider(
        name=name,
        endpoint=data.endpoint.strip(),
        model=data.model.strip(),
        api_key=(data.api_key or "").strip() or None,
        timeout_sec=data.timeout_sec,
        enabled=data.enabled,
        is_default=data.is_default,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return LlmProviderOut(
        id=f"custom:{row.id}",
        source="custom",
        name=row.name,
        endpoint=row.endpoint,
        model=row.model,
        timeout_sec=row.timeout_sec,
        enabled=row.enabled,
        is_default=row.is_default,
        has_api_key=bool(row.api_key),
    )


@router.patch("/{provider_id}", response_model=LlmProviderOut)
async def update_provider(
    provider_id: int,
    data: LlmProviderUpdate,
    session: AsyncSession = Depends(get_session),
):
    row = await _get_custom_or_404(session, provider_id)
    payload = data.model_dump(exclude_unset=True)
    if "endpoint" in payload:
        _assert_endpoint_safe(str(payload["endpoint"]).strip())
    if payload.get("is_default") is True:
        for x in (await session.execute(select(LlmProvider))).scalars():
            x.is_default = False
    if "endpoint" in payload:
        row.endpoint = str(payload["endpoint"]).strip()
    if "model" in payload:
        row.model = str(payload["model"]).strip()
    if "timeout_sec" in payload:
        row.timeout_sec = int(payload["timeout_sec"])
    if "enabled" in payload:
        row.enabled = bool(payload["enabled"])
    if "is_default" in payload:
        row.is_default = bool(payload["is_default"])
    if "api_key" in payload:
        row.api_key = (payload["api_key"] or "").strip() or None
    await session.commit()
    await session.refresh(row)
    return LlmProviderOut(
        id=f"custom:{row.id}",
        source="custom",
        name=row.name,
        endpoint=row.endpoint,
        model=row.model,
        timeout_sec=row.timeout_sec,
        enabled=row.enabled,
        is_default=row.is_default,
        has_api_key=bool(row.api_key),
    )


@router.delete("/{provider_id}")
async def delete_provider(provider_id: int, session: AsyncSession = Depends(get_session)):
    row = await _get_custom_or_404(session, provider_id)
    await session.delete(row)
    await session.commit()
    return {"ok": True}


@router.post("/{provider_name}/test", response_model=LlmProviderTestResponse)
async def test_provider_by_name(
    provider_name: str, session: AsyncSession = Depends(get_session)
):
    try:
        provider = await resolve_provider(session, preferred=provider_name)
    except LLMProviderNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    # Already-stored providers were validated at save time; reuse the fast cap.
    ok, detail = await provider.ping_with_detail()
    return LlmProviderTestResponse(
        ok=ok,
        provider=provider.name,
        detail=detail,
    )


@router.post("/test", response_model=LlmProviderTestResponse)
async def test_provider_raw(
    data: LlmProviderTestRequest, session: AsyncSession = Depends(get_session)
):
    if data.provider:
        try:
            provider = await resolve_provider(session, preferred=data.provider)
        except LLMProviderNotFound as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        ok, detail = await provider.ping_with_detail(
            timeout_override=float(data.timeout_sec)
        )
    else:
        if not data.endpoint or not data.model:
            raise HTTPException(
                status_code=400,
                detail="provider or (endpoint + model) is required",
            )
        # User-supplied URL → SSRF guard before we ever open a socket.
        _assert_endpoint_safe(data.endpoint)
        provider = OllamaProvider(
            name="adhoc",
            url=data.endpoint,
            model=data.model,
            timeout=data.timeout_sec,
            chat_endpoint=data.endpoint,
            api_key=data.api_key,
        )
        # Honour the caller's requested timeout exactly for adhoc probes.
        ok, detail = await provider.ping_with_detail(
            timeout_override=float(data.timeout_sec)
        )
    return LlmProviderTestResponse(
        ok=ok,
        provider=provider.name,
        detail=detail,
    )
