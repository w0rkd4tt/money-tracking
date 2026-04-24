from datetime import datetime

from pydantic import BaseModel, Field


class UnlockStatus(BaseModel):
    configured: bool
    unlocked: bool


class SetupRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=128)


class SetupResponse(BaseModel):
    ok: bool = True
    # Shown ONCE at setup. User must save (print, write, password manager).
    # Lost → can only reset passphrase via in-process "I forgot" flow if still
    # unlocked; otherwise data narrative is not encrypted so nothing is lost,
    # but the passphrase gate becomes un-resettable until DB reset.
    recovery_key: str
    expires_at: datetime


class UnlockRequest(BaseModel):
    passphrase: str = Field(min_length=1, max_length=128)


class UnlockResponse(BaseModel):
    ok: bool = True
    expires_at: datetime


class ChangePassphraseRequest(BaseModel):
    old_passphrase: str = Field(min_length=1, max_length=128)
    new_passphrase: str = Field(min_length=8, max_length=128)


class ChangePassphraseResponse(BaseModel):
    ok: bool = True
    # Rotating the passphrase also rotates the recovery key.
    new_recovery_key: str


class RecoverRequest(BaseModel):
    recovery_key: str = Field(min_length=10, max_length=128)
    new_passphrase: str = Field(min_length=8, max_length=128)


class RecoverResponse(BaseModel):
    ok: bool = True
    new_recovery_key: str
    expires_at: datetime
