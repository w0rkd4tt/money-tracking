"""WebAuthn (passkey) service.

Second authentication path alongside the 6-digit PIN. A user may enrol many
passkeys (Touch ID, Face ID, Windows Hello, YubiKey) and unlock with any of
them — each row in `ui_passkey` is one authenticator.

Ceremony state (the random challenge issued at /begin, consumed at /finish)
lives in an in-memory dict with 5-minute TTL. Lost across restarts — the
client retries. A single process is assumed (compose runs 1 api replica).

Relying Party (RP) identity is pinned to `localhost` for the dev deployment.
WebAuthn only accepts http for origin = localhost; LAN/Tailscale access
(100.x IPs) would need TLS to extend this.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..models import UiPasskey

# ---------------------------------------------------------------------------
# Relying Party
# ---------------------------------------------------------------------------
RP_ID = "localhost"
RP_NAME = "Money Tracking"
EXPECTED_ORIGINS: list[str] = ["http://localhost:3000"]
# Stable per-install user handle (WebAuthn binds credentials to this). We only
# have one user so any unique bytes string works; keep it constant so re-enrol
# after reset still resolves to the same "account" in the browser UI.
USER_HANDLE: bytes = b"money-tracking-single-user-001"[:16]
USER_NAME = "money-tracking"
USER_DISPLAY_NAME = "Money Tracking"


# ---------------------------------------------------------------------------
# Challenge store (ephemeral in-memory)
# ---------------------------------------------------------------------------
@dataclass
class _Pending:
    challenge: bytes
    created_at: float = field(default_factory=time.time)


_CHALLENGE_TTL_SEC = 5 * 60
_pending: dict[str, _Pending] = {}


def _new_state_id() -> str:
    return secrets.token_urlsafe(16)


def _prune_challenges(now: float | None = None) -> None:
    now = now or time.time()
    stale = [k for k, v in _pending.items() if now - v.created_at > _CHALLENGE_TTL_SEC]
    for k in stale:
        _pending.pop(k, None)


# ---------------------------------------------------------------------------
# Registration ceremony
# ---------------------------------------------------------------------------
async def start_registration(session: AsyncSession) -> tuple[str, dict[str, Any]]:
    """Return (state_id, options) to hand to the browser.

    Browser calls `navigator.credentials.create()` with `options`, then POSTs
    the result + state_id back to /register/finish.
    """
    _prune_challenges()
    rows = (await session.execute(select(UiPasskey.credential_id))).scalars().all()
    # exclude_credentials tells the browser not to let the user enrol the same
    # authenticator twice (otherwise Touch ID silently succeeds with the old
    # credential and DB grows a duplicate).
    existing = [PublicKeyCredentialDescriptor(id=bytes(r)) for r in rows]

    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=USER_HANDLE,
        user_name=USER_NAME,
        user_display_name=USER_DISPLAY_NAME,
        exclude_credentials=existing,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Prefer a discoverable credential stored on the authenticator so
            # the browser can offer it without knowing the credential id up
            # front — but don't require it (security keys without resident
            # storage should still work).
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    state_id = _new_state_id()
    _pending[state_id] = _Pending(challenge=options.challenge)
    return state_id, json.loads(options_to_json(options))


async def finish_registration(
    session: AsyncSession,
    state_id: str,
    response_json: dict[str, Any],
    name: str,
) -> UiPasskey:
    _prune_challenges()
    state = _pending.pop(state_id, None)
    if not state:
        raise ValueError("registration challenge expired or unknown")

    verified = verify_registration_response(
        credential=response_json,
        expected_challenge=state.challenge,
        expected_origin=EXPECTED_ORIGINS,
        expected_rp_id=RP_ID,
        require_user_verification=False,
    )

    transports_str: str | None = None
    raw_transports = response_json.get("response", {}).get("transports")
    if isinstance(raw_transports, list) and raw_transports:
        transports_str = ",".join(t for t in raw_transports if isinstance(t, str))[:120]

    pk = UiPasskey(
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=(name.strip() or "Passkey")[:80],
        transports=transports_str,
    )
    session.add(pk)
    await session.flush()
    return pk


# ---------------------------------------------------------------------------
# Authentication ceremony
# ---------------------------------------------------------------------------
async def start_authentication(session: AsyncSession) -> tuple[str, dict[str, Any]]:
    _prune_challenges()
    rows = (await session.execute(select(UiPasskey.credential_id))).scalars().all()
    if not rows:
        raise ValueError("no passkeys registered")
    allow = [PublicKeyCredentialDescriptor(id=bytes(r)) for r in rows]

    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    state_id = _new_state_id()
    _pending[state_id] = _Pending(challenge=options.challenge)
    return state_id, json.loads(options_to_json(options))


async def finish_authentication(
    session: AsyncSession,
    state_id: str,
    response_json: dict[str, Any],
) -> UiPasskey:
    _prune_challenges()
    state = _pending.pop(state_id, None)
    if not state:
        raise ValueError("authentication challenge expired or unknown")

    raw_cred_id = response_json.get("id") or response_json.get("rawId")
    if not raw_cred_id:
        raise ValueError("missing credential id in response")
    cred_id = base64url_to_bytes(raw_cred_id)
    pk = (
        await session.execute(
            select(UiPasskey).where(UiPasskey.credential_id == cred_id)
        )
    ).scalar_one_or_none()
    if not pk:
        raise ValueError("unknown credential")

    verified = verify_authentication_response(
        credential=response_json,
        expected_challenge=state.challenge,
        expected_origin=EXPECTED_ORIGINS,
        expected_rp_id=RP_ID,
        credential_public_key=bytes(pk.public_key),
        credential_current_sign_count=pk.sign_count,
        require_user_verification=False,
    )

    # Spec says: if new_sign_count <= stored, the authenticator *may* be
    # cloned. Platform authenticators (Touch ID) often return 0 forever →
    # tolerate. Security keys with real counters increment strictly.
    pk.sign_count = verified.new_sign_count
    pk.last_used_at = datetime.utcnow()
    return pk


# ---------------------------------------------------------------------------
# List / delete / count
# ---------------------------------------------------------------------------
async def list_passkeys(session: AsyncSession) -> list[UiPasskey]:
    rows = (
        await session.execute(
            select(UiPasskey).order_by(UiPasskey.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def delete_passkey(session: AsyncSession, passkey_id: int) -> bool:
    result = await session.execute(
        delete(UiPasskey).where(UiPasskey.id == passkey_id)
    )
    return (result.rowcount or 0) > 0


async def count_passkeys(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count(UiPasskey.id)))
    return int(n or 0)
