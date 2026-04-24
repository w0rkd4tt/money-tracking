"""Google OAuth endpoints: start consent, handle callback, disconnect.

Flow:
  1. Browser → GET /api/v1/oauth/google/start
  2. API → build consent URL, 307 redirect to Google
  3. User approves
  4. Google → GET /api/v1/oauth/google/callback?code=...&state=...
  5. API → exchange code, encrypt+store refresh_token, redirect to web settings
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..ingest.gmail_oauth import (
    delete_credentials,
    exchange_code,
    generate_auth_url,
    get_connected_email,
)
from ..ingest.gmail_oauth import save_credentials as save_google_credentials
from ..models import SyncState

log = logging.getLogger(__name__)
router = APIRouter(prefix="/oauth/google", tags=["oauth"])


def _pkce_key(state: str) -> str:
    return f"oauth.pkce.{state}"


@router.get("/start")
async def start(session: AsyncSession = Depends(get_session)):
    try:
        url, state, code_verifier = generate_auth_url()
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    # Persist verifier keyed by state — callback rebuilds Flow and needs it
    # to satisfy the PKCE challenge Google stored at the start step.
    session.add(SyncState(key=_pkce_key(state), value=code_verifier))
    await session.commit()
    return RedirectResponse(url=url, status_code=307)


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.execute(select(SyncState).where(SyncState.key == _pkce_key(state)))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(400, "OAuth state expired or unknown — restart the flow")
    verifier = row.value

    # Always consume the PKCE entry to block replay — even on exchange failure
    # the user must restart.
    try:
        creds = exchange_code(code, state, code_verifier=verifier)
    except Exception as e:
        log.error("OAuth exchange failed: %s", e)
        await session.execute(
            delete(SyncState).where(SyncState.key == _pkce_key(state))
        )
        await session.commit()
        raise HTTPException(400, f"OAuth exchange failed: {e}") from e
    else:
        await session.execute(
            delete(SyncState).where(SyncState.key == _pkce_key(state))
        )

    # Fetch the user's email via Gmail profile
    from google.auth.transport.requests import Request as GoogleRequest
    from googleapiclient.discovery import build

    try:
        if not creds.valid:
            creds.refresh(GoogleRequest())
        svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        prof = svc.users().getProfile(userId="me").execute()
        email = prof.get("emailAddress", "unknown@example.com")
    except Exception as e:
        log.error("failed to fetch Gmail profile: %s", e)
        raise HTTPException(500, f"failed to read profile: {e}") from e

    try:
        await save_google_credentials(session, email, creds)
        await session.commit()
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e

    # Redirect back to web settings with a success flag
    return RedirectResponse(
        url=f"http://localhost:3000/settings?google=ok&email={email}", status_code=303
    )


@router.delete("")
async def disconnect(session: AsyncSession = Depends(get_session)):
    removed = await delete_credentials(session)
    await session.commit()
    return {"disconnected": removed}


@router.get("/email")
async def current_email(session: AsyncSession = Depends(get_session)):
    email = await get_connected_email(session)
    return {"email": email}
