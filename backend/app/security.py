import hashlib
import hmac
import os
import re
import secrets
from datetime import timedelta

import jwt

from . import clock
from .config import Settings

ALGORITHM = "HS256"
_DEV_SECRET = secrets.token_urlsafe(48)  # per-process; tokens do not survive a restart in dev

_PHONE = re.compile(r"^[6-9]\d{9}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s\-()]", "", raw)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not _PHONE.match(digits):
        raise ValueError("enter a valid 10-digit Indian mobile number")
    return digits


def _secret(settings: Settings) -> str:
    return settings.jwt_secret or _DEV_SECRET


def issue_token(settings: Settings, subject: int, role: str) -> str:
    now = clock.now()
    payload = {"sub": str(subject), "role": role, "iat": now, "exp": now + timedelta(minutes=settings.jwt_ttl_minutes)}
    return jwt.encode(payload, _secret(settings), algorithm=ALGORITHM)


def decode_token(settings: Settings, token: str) -> dict:
    """Raises jwt.PyJWTError for any invalid, expired or tampered token."""
    return jwt.decode(token, _secret(settings), algorithms=[ALGORITHM], options={"require": ["exp", "sub", "role"]})


def hash_code(settings: Settings, phone: str, code: str) -> str:
    return hmac.new(_secret(settings).encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


def sign_webhook(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_webhook(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    return hmac.compare_digest(sign_webhook(secret, body), signature)
