import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import LargeBinary, TypeDecorator

from ..config import get_settings


def _key() -> bytes:
    raw = get_settings().app_encryption_key
    # Normalize: base64 if looks b64, else hash pad to 32 bytes
    try:
        b = base64.urlsafe_b64decode(raw + "==")
    except Exception:
        b = raw.encode()
    if len(b) < 32:
        b = (b * ((32 // len(b)) + 1))[:32]
    return b[:32]


def encrypt(plaintext: str) -> bytes:
    aes = AESGCM(_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct


def decrypt(blob: bytes) -> str:
    aes = AESGCM(_key())
    nonce, ct = blob[:12], blob[12:]
    return aes.decrypt(nonce, ct, None).decode("utf-8")


class EncryptedString(TypeDecorator):
    """Transparent AES-GCM encryption at rest for secret string columns.

    Reads/writes Python `str`; stores as `BYTEA`/`BLOB`. Uses `APP_ENCRYPTION_KEY`.
    Empty string is coerced to NULL (to avoid storing "" as a ciphertext).
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return None
        return encrypt(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt(bytes(value))
