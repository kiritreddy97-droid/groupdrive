from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import ratelimit
from .config import Settings, get_settings
from .db import get_db
from .models import Buyer, Dealer
from .otp import OtpSender, build_sender
from .payments import PaymentGateway, build_gateway
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


@lru_cache
def settings_dep() -> Settings:
    return get_settings()


@lru_cache
def otp_sender_dep() -> OtpSender:
    return build_sender(settings_dep().otp_sender)


@lru_cache
def payments_dep() -> PaymentGateway:
    return build_gateway(settings_dep().payment_provider)


def global_rate_limit(request: Request, settings: Settings = Depends(settings_dep)) -> None:
    if request.url.path.startswith("/webhooks/") or request.url.path == "/health":
        return
    ratelimit.enforce(request, settings, "global", settings.rate_limit_per_minute, 60)


@dataclass
class Principal:
    role: str  # buyer | dealer | admin
    id: Any  # buyer/dealer id, or the phone number for admins
    obj: Any = None  # Buyer or Dealer row


def _unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def require_roles(*roles: str):
    """Dependency factory: 401 without a valid token, 403 for a valid token of the wrong role."""

    def dependency(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                   settings: Settings = Depends(settings_dep), db: Session = Depends(get_db)) -> Principal:
        if creds is None:
            raise _unauthorized()
        try:
            claims = decode_token(settings, creds.credentials)
        except jwt.PyJWTError:
            raise _unauthorized("invalid or expired token") from None
        role, sub = claims["role"], claims["sub"]
        if role not in roles:
            raise HTTPException(403, "not allowed for this role")
        if role == "admin":
            if sub not in settings.admin_phones:
                raise _unauthorized("invalid or expired token")
            return Principal("admin", sub)
        model = Buyer if role == "buyer" else Dealer
        obj = db.get(model, int(sub))
        if obj is None or (role == "dealer" and not obj.active):
            raise _unauthorized("invalid or expired token")
        return Principal(role, obj.id, obj)

    return dependency


buyer_only = require_roles("buyer")
dealer_only = require_roles("dealer")
admin_only = require_roles("admin")
dealer_or_admin = require_roles("dealer", "admin")
