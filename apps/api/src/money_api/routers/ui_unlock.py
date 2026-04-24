"""Web UI unlock gate.

Public endpoints (no auth required). Provides:
- Status probe for middleware
- First-time setup (passphrase + one-time recovery key)
- Unlock (create session)
- Logout (delete session)
- Change passphrase (requires current passphrase)
- Recover (reset passphrase via recovery key)

Session is a httponly SameSite=Strict cookie `mt_session`. API data endpoints
are NOT gated — this is a UI convenience lock per single-user threat model.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..schemas.ui_unlock import (
    ChangePassphraseRequest,
    ChangePassphraseResponse,
    RecoverRequest,
    RecoverResponse,
    SetupRequest,
    SetupResponse,
    UnlockRequest,
    UnlockResponse,
    UnlockStatus,
)
from ..services.ui_unlock import (
    SESSION_SECONDS,
    create_session,
    delete_session,
    get_credential,
    locked,
    prune_expired_sessions,
    record_failure,
    remaining_attempts,
    reset_attempts,
    rotate_passphrase,
    setup_credential,
    verify_passphrase,
    verify_recovery_key,
    verify_session,
)

COOKIE_NAME = "mt_session"
router = APIRouter(prefix="/ui", tags=["ui-unlock"])


def _cookie_kwargs() -> dict:
    s = get_settings()
    return {
        "httponly": True,
        "samesite": "strict",
        "secure": s.app_env == "production",
        "path": "/",
    }


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/status", response_model=UnlockStatus)
async def status(
    session: AsyncSession = Depends(get_session),
    mt_session: str | None = Cookie(default=None),
):
    cred = await get_credential(session)
    unlocked = False
    if cred and mt_session:
        unlocked = (await verify_session(session, mt_session)) is not None
    return UnlockStatus(configured=cred is not None, unlocked=unlocked)


@router.post("/setup", response_model=SetupResponse, status_code=201)
async def setup(
    data: SetupRequest,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    if await get_credential(session):
        raise HTTPException(409, "already configured")
    result = await setup_credential(session, data.passphrase)
    ua = request.headers.get("user-agent", "")
    s = await create_session(session, user_agent=ua)
    response.set_cookie(
        COOKIE_NAME, s.raw_token, max_age=SESSION_SECONDS, **_cookie_kwargs()
    )
    await session.commit()
    return SetupResponse(recovery_key=result.recovery_key, expires_at=s.expires_at)


@router.post("/unlock", response_model=UnlockResponse)
async def unlock(
    data: UnlockRequest,
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
    cred = await get_credential(session)
    if not cred:
        raise HTTPException(409, "ui not configured; call /ui/setup first")
    if not verify_passphrase(cred.passphrase_hash, data.passphrase):
        record_failure(ip)
        raise HTTPException(
            401, f"invalid passphrase (remaining attempts: {remaining_attempts(ip)})"
        )
    reset_attempts(ip)
    await prune_expired_sessions(session)
    ua = request.headers.get("user-agent", "")
    s = await create_session(session, user_agent=ua)
    response.set_cookie(
        COOKIE_NAME, s.raw_token, max_age=SESSION_SECONDS, **_cookie_kwargs()
    )
    await session.commit()
    return UnlockResponse(expires_at=s.expires_at)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    mt_session: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    if mt_session:
        await delete_session(session, mt_session)
        await session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return None


@router.post("/change-passphrase", response_model=ChangePassphraseResponse)
async def change_passphrase_endpoint(
    data: ChangePassphraseRequest,
    response: Response,
    request: Request,
    mt_session: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_session),
):
    cred = await get_credential(session)
    if not cred:
        raise HTTPException(409, "ui not configured")
    # Require current session (so stranger with stolen passphrase can't rotate remotely)
    if not mt_session or not await verify_session(session, mt_session):
        raise HTTPException(401, "must be unlocked to change passphrase")
    if not verify_passphrase(cred.passphrase_hash, data.old_passphrase):
        raise HTTPException(401, "current passphrase mismatch")
    new_recovery = await rotate_passphrase(session, cred, data.new_passphrase)
    # Issue a fresh session (all old sessions including this one were wiped)
    ua = request.headers.get("user-agent", "")
    s = await create_session(session, user_agent=ua)
    response.set_cookie(
        COOKIE_NAME, s.raw_token, max_age=SESSION_SECONDS, **_cookie_kwargs()
    )
    await session.commit()
    return ChangePassphraseResponse(new_recovery_key=new_recovery)


@router.post("/recover", response_model=RecoverResponse)
async def recover(
    data: RecoverRequest,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    ip = _client_ip(request)
    if locked(ip):
        raise HTTPException(
            429,
            f"too many failed recovery attempts from this IP; wait 15 minutes",
        )
    cred = await get_credential(session)
    if not cred:
        raise HTTPException(409, "ui not configured")
    if not verify_recovery_key(cred, data.recovery_key):
        record_failure(ip)
        raise HTTPException(
            401, f"invalid recovery key (remaining attempts: {remaining_attempts(ip)})"
        )
    reset_attempts(ip)
    new_recovery = await rotate_passphrase(session, cred, data.new_passphrase)
    ua = request.headers.get("user-agent", "")
    s = await create_session(session, user_agent=ua)
    response.set_cookie(
        COOKIE_NAME, s.raw_token, max_age=SESSION_SECONDS, **_cookie_kwargs()
    )
    await session.commit()
    return RecoverResponse(new_recovery_key=new_recovery, expires_at=s.expires_at)
