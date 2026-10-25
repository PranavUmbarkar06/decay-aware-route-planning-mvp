"""Auth (ADR-010): phone + OTP → short-lived JWT; RBAC on every endpoint.

`auth.mode: dev_stub` returns the OTP in the API response (and the UI shows a DEV AUTH banner). A real SMS provider
plugs in behind `OtpSender` (INTEGRATIONS_TODO.md); none is implemented, and none is pretended.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import app_config
from app.core.db import get_db
from app.models.orm import User

log = logging.getLogger("phl.security")
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class Role(StrEnum):
    FARMER = "FARMER"
    SUPERVISOR = "SUPERVISOR"          # collection supervisor
    WAREHOUSE = "WAREHOUSE"            # warehouse / cold-storage owner
    DISPATCHER = "DISPATCHER"          # commission agent / trader / FPO marketing staff
    NGO = "NGO"                        # NGO / community-kitchen coordinator
    TRANSPORTER = "TRANSPORTER"        # driver: scan-only
    ADMIN = "ADMIN"                    # admin / analyst: read-all, run simulations


ROLE_DESCRIPTIONS = {
    Role.FARMER: "I grow produce and hand it to a collection centre or mandi.",
    Role.SUPERVISOR: "I run a collection centre: I receive, weigh and dispatch lots.",
    Role.WAREHOUSE: "I own or manage a warehouse or cold store.",
    Role.DISPATCHER: "I decide where and when loads go (commission agent, trader, FPO staff).",
    Role.NGO: "I coordinate an NGO or community kitchen that can take surplus food.",
    Role.TRANSPORTER: "I drive the truck. I scan lots at pickup and drop.",
    Role.ADMIN: "I analyse data and run simulations for the organisation.",
}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


_DEV_SECRET = secrets.token_hex(32)


def jwt_secret() -> str:
    s = os.environ.get(app_config().auth.jwt_secret_env)
    if s:
        return s
    if app_config().auth.mode != "dev_stub":
        raise RuntimeError(f"{app_config().auth.jwt_secret_env} must be set outside dev_stub mode")
    return _DEV_SECRET


def issue_token(user: User) -> str:
    now = utcnow()
    payload = {"sub": user.id, "role": user.role, "iat": now, "exp": now + timedelta(seconds=app_config().auth.jwt_ttl_s),
               "jti": uuid.uuid4().hex}
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


# ---------------------------------------------------------------- OTP
class OtpSender(Protocol):
    def send(self, phone: str, code: str) -> dict: ...


class DevStubSender:
    """Prints the OTP and returns it to the caller. DEV ONLY."""
    def send(self, phone: str, code: str) -> dict:
        log.warning("DEV AUTH: OTP for %s is %s (dev_stub mode, not sent by SMS)", phone[-4:].rjust(len(phone), "*"), code)
        return {"dev_otp": code, "delivery": "dev_stub (not sent)"}


def otp_sender() -> OtpSender:
    if app_config().auth.mode == "dev_stub":
        return DevStubSender()
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "No SMS provider configured (see docs/INTEGRATIONS_TODO.md)")


def hash_otp(phone: str, code: str) -> str:
    return hmac.new(jwt_secret().encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


# ---------------------------------------------------------------- dependencies
bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(creds.credentials, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    user = db.get(User, payload["sub"])
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require(*roles: Role):
    """Dependency factory: the user must have one of `roles` (ADMIN always allowed)."""
    allowed = {r.value for r in roles} | {Role.ADMIN.value}

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role {user.role} cannot do this")
        return user
    return dep


ANY_ROLE = tuple(Role)
