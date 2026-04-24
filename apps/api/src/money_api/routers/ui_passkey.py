"""WebAuthn / passkey endpoints.

Two ceremonies, each a begin/finish pair:
- /register/begin + /register/finish (requires unlocked session): add a new
  authenticator to the user's account.
- /auth/begin + /auth/finish (public, rate-limited): unlock the UI with a
  registered passkey. On success, issues the same `mt_session` cookie as the
  PIN flow.

Plus list + delete for the settings UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.ui_passkey import (
    delete_passkey,
    finish_authentication,
    finish_registration,
    list_passkeys,
    start_authentication,
    start_registration,
)
from ..services.ui_unlock import (
    SESSION_SECONDS,
    create_session,
    locked,
    prune_expired_sessions,
    record_failure,
    remaining_attempts,
    reset_attempts,
    verify_session,
)
from .ui_unlock import COOKIE_NAME, _client_ip, _cookie_kwargs

router = APIRouter(prefix="/ui/passkey", tags=["ui-passkey"])


class RegisterBeginResponse(BaseModel):
    state_id: str
    options: dict[str, Any]


class RegisterFinishRequest(BaseModel):
    state_id: str
    response: dict[str, Any]
    name: str = Field(min_length=1, max_length=80)


class PasskeyOut(BaseModel):
    id: int
    name: str
    transports: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuthBeginResponse(BaseModel):
    state_id: str
    options: dict[str, Any]


class AuthFinishRequest(BaseModel):
    state_id: str
    response: dict[str, Any]


class AuthFinishResponse(BaseModel):
    ok: bool = True
    expires_at: datetime
    passkey_id: int


@router.post("/register/begin", response_model=RegisterBeginResponse)
async def register_begin(
    mt_session: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    if not mt_session or not await verify_session(session, mt_session):
        raise HTTPException(401, "must be unlocked to register a passkey")
    state_id, options = await start_registration(session)
    return RegisterBeginResponse(state_id=state_id, options=options)


@router.post("/register/finish", response_model=PasskeyOut, status_code=201)
async def register_finish(
    data: RegisterFinishRequest,
    mt_session: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    if not mt_session or not await verify_session(session, mt_session):
        raise HTTPException(401, "must be unlocked to register a passkey")
    try:
        pk = await finish_registration(session, data.state_id, data.response, data.name)
    except Exception as e:
        raise HTTPException(400, f"registration failed: {e}") from e
    await session.commit()
    return pk


@router.post("/auth/begin", response_model=AuthBeginResponse)
async def auth_begin(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    ip = _client_ip(request)
    if locked(ip):
        raise HTTPException(
            429,
            f"too many failed attempts from this IP; wait 15 minutes "
            f"(remaining: {remaining_attempts(ip)})",
        )
    try:
        state_id, options = await start_authentication(session)
    except ValueError:
        raise HTTPException(409, "no passkeys registered; use PIN") from None
    return AuthBeginResponse(state_id=state_id, options=options)


@router.post("/auth/finish", response_model=AuthFinishResponse)
async def auth_finish(
    data: AuthFinishRequest,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    ip = _client_ip(request)
    if locked(ip):
        raise HTTPException(
            429,
            f"too many failed attempts from this IP; wait 15 minutes "
            f"(remaining: {remaining_attempts(ip)})",
        )
    try:
        pk = await finish_authentication(session, data.state_id, data.response)
    except Exception:
        record_failure(ip)
        raise HTTPException(
            401,
            f"passkey verification failed "
            f"(remaining attempts: {remaining_attempts(ip)})",
        ) from None

    reset_attempts(ip)
    await prune_expired_sessions(session)
    ua = request.headers.get("user-agent", "")
    s = await create_session(session, user_agent=ua)
    response.set_cookie(
        COOKIE_NAME, s.raw_token, max_age=SESSION_SECONDS, **_cookie_kwargs()
    )
    await session.commit()
    return AuthFinishResponse(expires_at=s.expires_at, passkey_id=pk.id)


@router.get("", response_model=list[PasskeyOut])
async def list_all(
    mt_session: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    if not mt_session or not await verify_session(session, mt_session):
        raise HTTPException(401, "must be unlocked")
    return await list_passkeys(session)


@router.delete("/{passkey_id}", status_code=204)
async def delete_one(
    passkey_id: int,
    mt_session: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    if not mt_session or not await verify_session(session, mt_session):
        raise HTTPException(401, "must be unlocked")
    ok = await delete_passkey(session, passkey_id)
    if not ok:
        raise HTTPException(404, "passkey not found")
    await session.commit()
    return None
