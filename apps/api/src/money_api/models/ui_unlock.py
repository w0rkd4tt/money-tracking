from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class UiCredential(Base):
    __tablename__ = "ui_credential"

    id: Mapped[int] = mapped_column(primary_key=True)
    passphrase_hash: Mapped[str] = mapped_column(String(255))
    recovery_key_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class UiSession(Base):
    __tablename__ = "ui_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class UiPasskey(Base):
    """One row per registered WebAuthn credential.

    A single user may enrol several devices (iPhone Face ID + MacBook Touch ID
    + Windows Hello + YubiKey). Each produces its own `credential_id` + public
    key; the password gate rotates PINs, passkeys are independent of that.
    """

    __tablename__ = "ui_passkey"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The WebAuthn credential identifier returned by the authenticator at
    # registration. Binary; unique per credential. Used to look up the public
    # key during the authentication ceremony.
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)  # COSE-encoded public key
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    # Friendly name so the user can tell passkeys apart in the settings UI
    # ("MacBook Air", "iPhone 15"). Filled by the user at registration.
    name: Mapped[str] = mapped_column(String(80))
    # Which transports the authenticator reported — affects how the browser
    # surfaces "use a security key" / "use your phone" prompts later.
    transports: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
