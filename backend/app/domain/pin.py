"""Consignment short code + backup PIN (see docs/SECURITY.md).

A 4-digit PIN alone has 10,000 combinations, so it is never accepted on its own:
- it only works together with the consignment's short code (8 chars, Crockford base32 ≈ 1.1e12 values);
- PINs are stored as salted PBKDF2 hashes, never in clear;
- failures are counted per consignment; after `max_failures` the PIN locks for `lockout_s`;
- the PIN expires `ttl_h` hours after issue;
- the API additionally rate-limits PIN attempts per client (core/ratelimit.py).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # no I, L, O, U: fewer misreadings
PBKDF2_ITER = 120_000


def new_short_code(n: int = 8) -> str:
    return "".join(secrets.choice(CROCKFORD) for _ in range(n))


def normalize_short_code(s: str) -> str:
    s = s.strip().upper().replace("-", "").replace(" ", "")
    return s.replace("O", "0").replace("I", "1").replace("L", "1")


def new_pin(digits: int = 4) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def hash_pin(pin: str, short_code: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", f"{short_code}:{pin}".encode(), salt, PBKDF2_ITER)
    return f"pbkdf2${PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def _check(pin: str, short_code: str, stored: str) -> bool:
    _, it, salt_hex, dk_hex = stored.split("$")
    dk = hashlib.pbkdf2_hmac("sha256", f"{short_code}:{pin}".encode(), bytes.fromhex(salt_hex), int(it))
    return hmac.compare_digest(dk.hex(), dk_hex)


@dataclass
class PinState:
    pin_hash: str
    issued_at: datetime
    failures: int = 0
    locked_until: datetime | None = None


@dataclass
class PinResult:
    ok: bool
    reason: str            # OK | WRONG_PIN | LOCKED | EXPIRED
    state: PinState


def verify_pin(pin: str, short_code: str, state: PinState, now: datetime, *, max_failures: int, lockout_s: int,
               ttl_h: int) -> PinResult:
    if state.locked_until and now < state.locked_until:
        return PinResult(False, "LOCKED", state)
    if now > state.issued_at + timedelta(hours=ttl_h):
        return PinResult(False, "EXPIRED", state)
    if _check(pin, short_code, state.pin_hash):
        return PinResult(True, "OK", PinState(state.pin_hash, state.issued_at, 0, None))
    failures = state.failures + 1
    locked = now + timedelta(seconds=lockout_s) if failures >= max_failures else None
    return PinResult(False, "LOCKED" if locked else "WRONG_PIN",
                     PinState(state.pin_hash, state.issued_at, 0 if locked else failures, locked))
