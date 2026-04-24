"""Google OAuth helpers for Gmail.

Uses scope `gmail.modify` — allows reading messages AND toggling the UNREAD
label so the poller can mark an email read after successfully ingesting it.
Does NOT permit sending or permanent deletion.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

# Tell oauthlib not to reject scope expansion. Google returns all previously-
# granted scopes for the account when `include_granted_scopes=true`, which
# oauthlib's strict check interprets as "scope changed" even though the set
# monotonically widens. Must be set BEFORE importing Flow.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request as GoogleRequest  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from google_auth_oauthlib.flow import Flow  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from ..config import get_settings  # noqa: E402
from ..models import OauthCredential
from ..services.crypto import decrypt, encrypt

log = logging.getLogger(__name__)

# Include both so Google's `include_granted_scopes=true` behaviour doesn't trip
# oauthlib's strict scope-equality check. When the user previously granted
# `gmail.readonly`, Google merges both in the returned scope set even though we
# only ask for `modify` — oauthlib then raises "Scope has changed…".
# Functionally `gmail.modify` is a superset of `gmail.readonly`, so listing both
# is redundant but explicit and safe.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
# Keep old scope name for migration detection in UI
LEGACY_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass
class StoredToken:
    refresh_token: str
    token: str | None
    token_uri: str
    client_id: str
    client_secret: str
    scopes: list[str]
    expiry: str | None = None


def _client_config() -> dict:
    s = get_settings()
    return {
        "web": {
            "client_id": s.google_client_id or "",
            "client_secret": s.google_client_secret or "",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [s.google_redirect_uri],
        }
    }


def build_flow(state: str | None = None) -> Flow:
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret):
        raise RuntimeError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set — configure OAuth in .env"
        )
    flow = Flow.from_client_config(
        _client_config(), scopes=SCOPES, state=state, redirect_uri=s.google_redirect_uri
    )
    return flow


def generate_auth_url() -> tuple[str, str, str]:
    """Return (auth_url, state, code_verifier).

    The caller must persist code_verifier keyed by state; the callback
    rebuilds a fresh Flow instance and needs to provide the verifier to
    satisfy the PKCE challenge Google stored from the start step.
    """
    flow = build_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return url, state, flow.code_verifier or ""


def exchange_code(
    code: str, state: str, code_verifier: str | None = None
) -> Credentials:
    flow = build_flow(state=state)
    if code_verifier:
        flow.code_verifier = code_verifier
    try:
        flow.fetch_token(code=code)
    except Warning as w:  # oauthlib raises Warning subclass for scope drift
        msg = str(w)
        if "Scope has changed" not in msg:
            raise
        # Scope set returned by Google is a superset of what we requested —
        # acceptable because we want both readonly + modify. Retry once with the
        # returned scopes authoritative.
        log.info("accepting scope expansion from Google: %s", msg)
        flow.fetch_token(code=code)
    return flow.credentials


async def save_credentials(session: AsyncSession, email: str, creds: Credentials) -> None:
    s = get_settings()
    payload = StoredToken(
        refresh_token=creds.refresh_token or "",
        token=creds.token,
        token_uri=creds.token_uri,
        client_id=s.google_client_id or "",
        client_secret=s.google_client_secret or "",
        scopes=list(creds.scopes or SCOPES),
        expiry=creds.expiry.isoformat() if creds.expiry else None,
    )
    if not payload.refresh_token:
        raise RuntimeError(
            "OAuth callback did not return a refresh_token — revoke consent at "
            "https://myaccount.google.com/permissions and try again with prompt=consent"
        )
    blob = encrypt(json.dumps(payload.__dict__))
    existing = (
        await session.execute(
            select(OauthCredential).where(
                OauthCredential.provider == "google", OauthCredential.account_email == email
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.encrypted_token = blob
        existing.scopes = " ".join(payload.scopes)
        existing.expires_at = creds.expiry
    else:
        session.add(
            OauthCredential(
                provider="google",
                account_email=email,
                encrypted_token=blob,
                scopes=" ".join(payload.scopes),
                expires_at=creds.expiry,
            )
        )
    await session.flush()


async def load_credentials(session: AsyncSession, email: str | None = None) -> Credentials | None:
    q = select(OauthCredential).where(OauthCredential.provider == "google")
    if email:
        q = q.where(OauthCredential.account_email == email)
    row = (await session.execute(q.limit(1))).scalar_one_or_none()
    if not row:
        return None
    data = json.loads(decrypt(row.encrypted_token))
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data.get("scopes") or SCOPES,
    )
    if not creds.valid:
        try:
            creds.refresh(GoogleRequest())
            data["token"] = creds.token
            data["expiry"] = creds.expiry.isoformat() if creds.expiry else None
            row.encrypted_token = encrypt(json.dumps(data))
            row.expires_at = creds.expiry
            await session.flush()
        except Exception as e:
            log.error("token refresh failed: %s", e)
            return None
    return creds


async def delete_credentials(session: AsyncSession, email: str | None = None) -> int:
    q = select(OauthCredential).where(OauthCredential.provider == "google")
    if email:
        q = q.where(OauthCredential.account_email == email)
    rows = (await session.execute(q)).scalars().all()
    for r in rows:
        await session.delete(r)
    return len(rows)


async def get_connected_email(session: AsyncSession) -> str | None:
    row = (
        await session.execute(
            select(OauthCredential.account_email)
            .where(OauthCredential.provider == "google")
            .limit(1)
        )
    ).first()
    return row[0] if row else None
