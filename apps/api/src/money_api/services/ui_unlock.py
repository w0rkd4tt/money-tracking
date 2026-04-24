"""UI unlock service.

Model:
- Single user. One row in `ui_credential` with passphrase_hash + recovery_key_hash.
  (Column is historically named `passphrase_hash`; it now stores the argon2id
  hash of a 6-digit PIN. Not renamed to avoid a migration — internal detail.)
- On web session start the user types a 6-digit PIN → `/ui/unlock` issues a
  session cookie `mt_session` (httponly, SameSite=Strict). Web middleware
  redirects based on cookie presence + `/ui/status`.
- The **API itself is not gated**. The gate protects only the web UI. This
  matches the single-user local-first threat model: we only care about
  "someone else opens my already-running browser".
- If the PIN is forgotten, a recovery key (shown ONCE at setup or rotation)
  can reset the PIN. DB data is plaintext so backups still restore cleanly.
- PIN keyspace is only 10^6, so security relies on the 5-attempts-per-15-min
  rate limiter + a bumped argon2 time_cost. For higher assurance, wire
  WebAuthn/passkey later (design anchor: add a second column
  `credential_type` + generic blob to support both PIN and passkey creds).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import UiCredential, UiSession

SESSION_DAYS = 30
SESSION_SECONDS = SESSION_DAYS * 24 * 3600

# time_cost bumped above argon2-cffi's default (3) to slow brute force against
# the tiny 10^6 PIN keyspace. Memory_cost at 64 MiB is standard; parallelism 1
# because we only ever verify a handful of PINs on a single process.
_ph = PasswordHasher(time_cost=4, memory_cost=65536, parallelism=1)


def hash_pin(raw: str) -> str:
    return _ph.hash(raw)


def verify_pin(hashed: str, raw: str) -> bool:
    try:
        _ph.verify(hashed, raw)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _new_recovery_key() -> str:
    """Generate a 160-bit recovery key formatted for readability.
    Example: `QX3K-ZP8H-MD2R-KV7W-9JL4-B6N2-AB7C-DE23`  (8 groups of 4 base32 chars)
    """
    import base64

    # 20 bytes = 160 bits of entropy; base32 → exactly 32 chars (no padding).
    raw = secrets.token_bytes(20)
    s = base64.b32encode(raw).decode("ascii")
    groups = [s[i : i + 4] for i in range(0, len(s), 4)]
    return "-".join(groups)


def _normalize_recovery_key(raw: str) -> str:
    """Strip hyphens/whitespace and uppercase so input matches stored hash."""
    return "".join(raw.split()).replace("-", "").upper()


# ---------------------------------------------------------------------------
# Credential
# ---------------------------------------------------------------------------


async def get_credential(session: AsyncSession) -> UiCredential | None:
    return (await session.execute(select(UiCredential).limit(1))).scalar_one_or_none()


@dataclass
class SetupResult:
    credential: UiCredential
    recovery_key: str


async def setup_credential(session: AsyncSession, pin: str) -> SetupResult:
    recovery = _new_recovery_key()
    cred = UiCredential(
        passphrase_hash=hash_pin(pin),
        recovery_key_hash=_sha256(_normalize_recovery_key(recovery)),
    )
    session.add(cred)
    await session.flush()
    return SetupResult(credential=cred, recovery_key=recovery)


async def rotate_pin(
    session: AsyncSession, cred: UiCredential, new_pin: str
) -> str:
    """Change PIN and rotate recovery key. Returns new recovery key.
    Invalidates ALL existing sessions.
    """
    new_recovery = _new_recovery_key()
    cred.passphrase_hash = hash_pin(new_pin)
    cred.recovery_key_hash = _sha256(_normalize_recovery_key(new_recovery))
    await session.execute(delete(UiSession))
    return new_recovery


def verify_recovery_key(cred: UiCredential, provided: str) -> bool:
    normalized = _normalize_recovery_key(provided)
    if not normalized:
        return False
    return secrets.compare_digest(cred.recovery_key_hash, _sha256(normalized))


# ---------------------------------------------------------------------------
# Sessions (cookie-based)
# ---------------------------------------------------------------------------


@dataclass
class IssuedSession:
    session_id: int
    raw_token: str
    expires_at: datetime


async def create_session(
    session: AsyncSession, user_agent: str | None = None
) -> IssuedSession:
    raw = _new_session_token()
    expires = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    row = UiSession(
        token_hash=_sha256(raw),
        expires_at=expires,
        user_agent=(user_agent or "")[:255] or None,
    )
    session.add(row)
    await session.flush()
    return IssuedSession(session_id=row.id, raw_token=raw, expires_at=expires)


async def verify_session(session: AsyncSession, raw: str) -> UiSession | None:
    if not raw:
        return None
    h = _sha256(raw)
    row = (
        await session.execute(select(UiSession).where(UiSession.token_hash == h))
    ).scalar_one_or_none()
    if not row:
        return None
    if row.expires_at <= datetime.utcnow():
        await session.delete(row)
        return None
    row.last_seen_at = datetime.utcnow()
    return row


async def delete_session(session: AsyncSession, raw: str) -> None:
    if not raw:
        return
    await session.execute(delete(UiSession).where(UiSession.token_hash == _sha256(raw)))


async def prune_expired_sessions(session: AsyncSession) -> None:
    await session.execute(delete(UiSession).where(UiSession.expires_at <= datetime.utcnow()))


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per-IP sliding window)
# ---------------------------------------------------------------------------

_LOGIN_WINDOW_SEC = 15 * 60
_LOGIN_MAX_ATTEMPTS = 5
_attempts: dict[str, deque[float]] = {}


def _prune(ip: str, now: float) -> None:
    q = _attempts.get(ip)
    if not q:
        return
    cutoff = now - _LOGIN_WINDOW_SEC
    while q and q[0] < cutoff:
        q.popleft()


def locked(ip: str) -> bool:
    now = time.time()
    _prune(ip, now)
    q = _attempts.get(ip) or deque()
    return len(q) >= _LOGIN_MAX_ATTEMPTS


def record_failure(ip: str) -> None:
    now = time.time()
    q = _attempts.setdefault(ip, deque())
    q.append(now)
    _prune(ip, now)


def reset_attempts(ip: str) -> None:
    _attempts.pop(ip, None)


def remaining_attempts(ip: str) -> int:
    now = time.time()
    _prune(ip, now)
    return max(0, _LOGIN_MAX_ATTEMPTS - len(_attempts.get(ip) or deque()))
