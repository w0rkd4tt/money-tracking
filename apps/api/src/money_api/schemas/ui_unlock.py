from datetime import datetime

from pydantic import BaseModel, Field

# 6-digit numeric PIN. Exact length enforced so clients can't accidentally send
# e.g. a long phrase or an empty string — Pydantic rejects with 422 before the
# request hits the rate limiter / hasher.
PIN_PATTERN = r"^\d{6}$"


class UnlockStatus(BaseModel):
    configured: bool
    unlocked: bool
    # Non-zero iff the user has enrolled at least one WebAuthn authenticator.
    # Drives the "Unlock with Touch ID" button on the unlock screen.
    passkey_count: int = 0


class SetupRequest(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=PIN_PATTERN)


class SetupResponse(BaseModel):
    ok: bool = True
    # Shown ONCE at setup. User must save (print, write, password manager).
    # PIN keyspace is tiny (1M combinations), so losing the recovery key + PIN
    # means wipe-and-reinitialise the UI credential table.
    recovery_key: str
    expires_at: datetime


class UnlockRequest(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=PIN_PATTERN)


class UnlockResponse(BaseModel):
    ok: bool = True
    expires_at: datetime


class ChangePinRequest(BaseModel):
    old_pin: str = Field(min_length=6, max_length=6, pattern=PIN_PATTERN)
    new_pin: str = Field(min_length=6, max_length=6, pattern=PIN_PATTERN)


class ChangePinResponse(BaseModel):
    ok: bool = True
    # Rotating the PIN also rotates the recovery key.
    new_recovery_key: str


class RecoverRequest(BaseModel):
    recovery_key: str = Field(min_length=10, max_length=128)
    new_pin: str = Field(min_length=6, max_length=6, pattern=PIN_PATTERN)


class RecoverResponse(BaseModel):
    ok: bool = True
    new_recovery_key: str
    expires_at: datetime
