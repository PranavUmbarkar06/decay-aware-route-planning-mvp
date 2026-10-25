"""Business clock.

Demo mode: starts at `runtime.demo_clock_utc` (inside the weather replay window, so every temperature the app uses is
replayed real data) when the process boots and then advances in real time, so countdowns (claim timers, undo
windows) behave normally. Outside demo mode it is the real UTC clock. Security timestamps (JWT, OTP) always use the
real clock (`core.security.utcnow`). Naive UTC datetimes throughout.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from app.core.config import app_config

_BOOT_REAL = datetime.now(UTC).replace(tzinfo=None)


def is_demo_clock() -> bool:
    rt = app_config().runtime
    return bool(rt.demo_mode and rt.demo_clock_utc and os.environ.get("PHL_CLOCK") != "real")


def now() -> datetime:
    real = datetime.now(UTC).replace(tzinfo=None)
    if is_demo_clock():
        start = datetime.fromisoformat(app_config().runtime.demo_clock_utc or "")
        return start + (real - _BOOT_REAL)
    return real
