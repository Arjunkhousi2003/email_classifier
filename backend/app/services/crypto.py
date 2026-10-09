import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

# Stable 32-byte key used only when DEV_MODE=true and ENCRYPTION_KEY is unset.
_DEV_KEY = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef")


def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.encryption_key.strip()
    if not raw or raw.startswith("replace-"):
        if not settings.dev_mode:
            raise RuntimeError("ENCRYPTION_KEY is required when DEV_MODE is false")
        logger.warning("Using the built-in development encryption key. Set ENCRYPTION_KEY before storing real tokens.")
        return Fernet(_DEV_KEY)
    return Fernet(raw.encode("utf-8"))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored secret could not be decrypted") from exc
