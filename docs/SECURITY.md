# Security notes

Scope: prototype. Not penetration-tested. Items marked TODO must be resolved before any pilot with real users.

## Consignment short code + backup PIN (M1)
A 4-digit PIN has only 10,000 combinations, so it is never a credential on its own.
| Control | Implementation (`backend/app/domain/pin.py`, API layer) |
|---|---|
| PIN only valid with the short code | 8-char Crockford base32 short code (32⁸ ≈ 1.1 × 10¹²); PIN hash is salted with the short code |
| Storage | PBKDF2-HMAC-SHA256, 120,000 iterations, 16-byte random salt; the PIN is shown once at creation and never stored in clear |
| Lockout | `pin.max_failures` (5) consecutive failures lock the PIN for `pin.lockout_s` (15 min) |
| Expiry | `pin.ttl_h` (72 h) after issue; the QR code remains the primary path |
| Rate limit | per-client limit on PIN endpoints (`pin.rate_limit_per_min`); 429 beyond it |
| Ambiguity | Crockford alphabet (no I/L/O/U); input normalised (O→0, I/L→1) |

Residual risk: an attacker who already has the short code (e.g. photographed the label) gets 5 guesses per 15 min,
i.e. at most 480 guesses/day; with 10,000 PINs this is ~5% per day of sustained guessing. **Mitigation in place:**
expiry at 72 h and every scan is logged with the actor. **TODO for pilot:** alert the owner on lockouts.

## Tamper-evident custody log (not a blockchain, ADR-012)
- Each custody event stores `prev_hash` and `hash = SHA-256(prev_hash | canonical event fields)`.
- **Finding during property testing:** a hash chain alone cannot detect deletion of its *last* events (tail
  truncation). The consignment row therefore records `chain_head` and `chain_count`; verification checks both.
- The chain detects edits/removals/reorders by anyone who can only modify event rows. It does **not** protect
  against an operator who can rewrite both the events and the consignment row (no external anchoring). **TODO
  (optional):** periodically publish head hashes to an external append-only store.

## Authentication (ADR-010)
- Phone + OTP. Demo/dev uses a stub provider that returns the OTP in the API response; the UI shows a "DEV AUTH"
  banner. **Never deploy with `auth.mode: dev_stub`.**
- OTP requests are rate-limited per client (`auth.otp_requests_per_min`): 5/min is the production default; the demo
  config sets 20/min so the guided demo can switch personas. **Restore 5 before any pilot.** `PHL_RATE_LIMIT_MULTIPLIER` is set only by the isolated E2E stack; never set it in a deployment.
- Short-lived JWT (`auth.jwt_ttl_s`); secret from env var `PHL_JWT_SECRET`, with a per-process random fallback in dev
  only (logged as DEV).
- RBAC is checked on every endpoint (role matrix tested in `test_api_rbac.py`).

## Other controls
- Input validation via pydantic models on every request.
- No secrets in git (`.env` ignored; `.env.example` documents variables).
- Dependency audit: `python tasks.py audit-deps` (pip-audit) and `npm audit` in CI.
- Audit log of every state change (who, what, when, before/after).

## Privacy (see COMPLIANCE_TODO.md)
Minimum personal data: phone number, role, optional name and district. A consent screen precedes registration.
India's data-protection law applies; legal review by counsel is a TODO (no legal conclusions are drawn here).
