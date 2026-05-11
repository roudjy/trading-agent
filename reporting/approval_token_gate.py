"""N4a — Approval Token Gate (pure mint/verify; no live wiring).

Pure stdlib-only HMAC-SHA256 token surface for the future PWA
mobile-approval flow. N4a defines the **closed token schema**,
the **deterministic minting** function, the **constant-time
verification** function, and the **replay-protected seen-set**
contract. It does **not**:

* read an HMAC secret from the operating-system environment;
* register a Flask blueprint or wire into ``dashboard/dashboard.py``;
* execute any approve / reject / merge / deploy action;
* call any HTTP / GitHub / push surface;
* send any real push notification;
* persist tokens to a server-side store.

The future N4b slice (operator-action-only) will:

* read ``ADE_<APPROVAL_TOKEN_ENV_VAR_NAME>`` from the VPS environment;
* register a Flask blueprint that calls :func:`mint_token` and
  :func:`verify_token` with the env-supplied secret;
* persist a server-side seen-nonce set for replay protection.

Until N4b lands and is operator-authorised, N4a is a *callable*
that exposes the cryptographic contract via explicit secret-passed
arguments only. Tests supply synthetic 32-byte secrets directly.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.agent_audit_summary.assert_no_secrets``
  (read-only redactor guard).
* No subprocess, no network, no ``gh``, no ``git``, no socket
  library, no Web Push library.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* No I/O at module level. ``mint_token`` and ``verify_token`` are
  pure — they take a secret as argument, never read it from env.
  The literal environment-variable name
  ``ADE_<APPROVAL_TOKEN_ENV_VAR_NAME>`` does NOT appear in this
  module's executable code.
* The closed token-claim schema contains NO decision verb. The
  ``intent`` claim uses ``mobile_approval_dispatch`` rather than
  ``approve`` / ``merge`` to make this unambiguous.
* The closed ``verify_outcome`` vocabulary makes every failure
  mode operator-visible.
* Tokens are bound to ``(event_id, pr_number, pr_head_sha,
  evidence_hash, release_tag)``. Drift in any binding invalidates
  the token at verify time.
* Expiry is enforced; ``DEFAULT_TTL_SECONDS = 900`` (15 min); the
  ``ttl_seconds`` argument cannot exceed ``MAX_TTL_SECONDS = 900``.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.

What N4a is for
---------------

Operators inspect the closed contract before authorising N4b. Tests
ship a synthetic secret to assert behaviour. No production code
path consumes N4a today — A23 only *recommends*; the recommendation
becomes actionable only when N4b wires this gate into a live
endpoint.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import secrets as _secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Final

MODULE_VERSION: Final[str] = "v3.15.16.N4a"
SCHEMA_VERSION: Final[str] = "1.0"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed token-intent vocabulary. Adding a value requires a code
#: change pinned by an updated unit test.
#:
#: **No decision verb in the closed set.** The intent is the
#: *purpose for which the token may be presented*, not the action a
#: caller can take with it. ``mobile_approval_dispatch`` is the
#: token a mobile operator presents to the future N5 surface to
#: *initiate* a merge — but the merge itself goes through additional
#: gates (branch protection, mergeable state, head_sha re-binding,
#: evidence_hash re-binding). The token is necessary but not
#: sufficient.
TOKEN_INTENTS: Final[tuple[str, ...]] = (
    "mobile_approval_dispatch",
    "mobile_review_dispatch",
)

#: Closed verify-outcome vocabulary.
VERIFY_OUTCOMES: Final[tuple[str, ...]] = (
    "ok",
    "expired",
    "signature_invalid",
    "binding_mismatch",
    "intent_unknown",
    "malformed_envelope",
    "replay_detected",
    "unknown_kid",
)

#: Closed claims-key schema. Mirrors what mint_token() emits.
TOKEN_CLAIM_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "intent",
    "event_id",
    "pr_number",
    "pr_head_sha",
    "evidence_hash",
    "release_tag",
    "kid",
    "nonce",
    "issued_at_utc",
    "expires_at_utc",
)

#: HMAC algorithm. Pinned at SHA-256; widening requires a code
#: change pinned by an updated test.
HMAC_ALGORITHM: Final[str] = "sha256"

#: Minimum acceptable secret length in bytes. 32 bytes = 256 bits.
MIN_SECRET_LENGTH_BYTES: Final[int] = 32

#: Default token lifetime. 15 min — short by design.
DEFAULT_TTL_SECONDS: Final[int] = 900

#: Maximum acceptable TTL. mint_token refuses any larger value.
MAX_TTL_SECONDS: Final[int] = 900

#: Token envelope separator. Tokens are
#: ``<base64url(claims_json)>.<base64url(signature_bytes)>``.
_TOKEN_SEPARATOR: Final[str] = "."

#: Required claim fields that participate in binding verification.
#: All five must match at verify time, in addition to the signature.
_BINDING_CLAIMS: Final[tuple[str, ...]] = (
    "event_id",
    "pr_number",
    "pr_head_sha",
    "evidence_hash",
    "release_tag",
)


# ---------------------------------------------------------------------------
# Public dataclass for verify_token's result
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class VerifyResult:
    """Pure result of :func:`verify_token`.

    Invariants:

    * ``outcome`` is in :data:`VERIFY_OUTCOMES`.
    * ``claims`` is the decoded claims dict when ``outcome == "ok"``,
      otherwise ``None``.
    * ``reason`` is a closed-vocabulary short string suitable for
      audit logging; never includes the offending token, signature,
      or secret material.
    """

    outcome: str
    claims: dict[str, Any] | None
    reason: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """URL-safe base64 without padding."""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    import base64

    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _validate_secret(secret: bytes) -> None:
    """Validate that the caller-supplied secret meets minimum length.

    The secret is supplied as ``bytes`` to avoid accidental string
    encoding ambiguity. Tests use ``secrets.token_bytes(32)``;
    production N4b will use the env-supplied bytes.
    """
    if not isinstance(secret, bytes):
        raise TypeError("secret must be bytes")
    if len(secret) < MIN_SECRET_LENGTH_BYTES:
        raise ValueError(
            f"secret must be at least {MIN_SECRET_LENGTH_BYTES} bytes; "
            f"got {len(secret)}"
        )


def _canonical_signing_payload(claims: dict[str, Any]) -> bytes:
    """Deterministic canonical JSON payload that the signature
    covers. Sorted keys, no whitespace."""
    return json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(claims: dict[str, Any], *, secret: bytes) -> bytes:
    payload = _canonical_signing_payload(claims)
    return hmac.new(secret, payload, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------


def mint_token(
    *,
    intent: str,
    event_id: str,
    pr_number: int | None,
    pr_head_sha: str | None,
    evidence_hash: str,
    release_tag: str | None,
    kid: str,
    secret: bytes,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Mint a closed-schema HMAC-SHA256 approval token.

    Returns the token as ``<b64url(claims_json)>.<b64url(signature)>``.
    """
    if intent not in TOKEN_INTENTS:
        raise ValueError(
            f"intent must be one of {TOKEN_INTENTS}; got {intent!r}"
        )
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")
    if pr_number is not None and not isinstance(pr_number, int):
        raise TypeError("pr_number must be int or None")
    if pr_head_sha is not None and not isinstance(pr_head_sha, str):
        raise TypeError("pr_head_sha must be str or None")
    if not isinstance(evidence_hash, str) or not evidence_hash:
        raise ValueError("evidence_hash must be a non-empty string")
    if release_tag is not None and not isinstance(release_tag, str):
        raise TypeError("release_tag must be str or None")
    if not isinstance(kid, str) or not kid:
        raise ValueError("kid must be a non-empty string")
    if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive int")
    if ttl_seconds > MAX_TTL_SECONDS:
        raise ValueError(
            f"ttl_seconds must be <= {MAX_TTL_SECONDS}; got {ttl_seconds}"
        )
    _validate_secret(secret)

    iat = now if now is not None else _utcnow()
    exp = iat + timedelta(seconds=ttl_seconds)
    nonce = _secrets.token_hex(16)

    claims: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "intent": intent,
        "event_id": event_id,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "evidence_hash": evidence_hash,
        "release_tag": release_tag,
        "kid": kid,
        "nonce": nonce,
        "issued_at_utc": _iso(iat),
        "expires_at_utc": _iso(exp),
    }
    # Closed shape check.
    assert set(claims.keys()) == set(TOKEN_CLAIM_KEYS)

    sig = _sign(claims, secret=secret)
    claims_b64 = _b64url_encode(_canonical_signing_payload(claims))
    sig_b64 = _b64url_encode(sig)
    return f"{claims_b64}{_TOKEN_SEPARATOR}{sig_b64}"


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_token(
    token: str,
    *,
    expected_event_id: str,
    expected_pr_number: int | None,
    expected_pr_head_sha: str | None,
    expected_evidence_hash: str,
    expected_release_tag: str | None,
    secrets_by_kid: dict[str, bytes],
    seen_nonces: set[str] | None = None,
    now: datetime | None = None,
) -> VerifyResult:
    """Constant-time HMAC verification with closed-vocab outcomes.

    The caller supplies the kid → secret lookup as an argument; N4a
    NEVER reads any environment variable. ``seen_nonces`` is an
    optional caller-managed replay-protection set: if the decoded
    ``nonce`` is already in it, the token is rejected with
    ``replay_detected``. (N4a does not mutate the set itself; the
    caller decides whether to record a verified nonce.)
    """
    # Envelope shape.
    if not isinstance(token, str) or _TOKEN_SEPARATOR not in token:
        return VerifyResult("malformed_envelope", None, "no_separator")
    try:
        claims_b64, sig_b64 = token.split(_TOKEN_SEPARATOR, 1)
        if not claims_b64 or not sig_b64:
            raise ValueError
    except ValueError:
        return VerifyResult("malformed_envelope", None, "split_failed")

    try:
        claims_json = _b64url_decode(claims_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:
        return VerifyResult("malformed_envelope", None, "base64_decode_failed")
    try:
        claims = json.loads(claims_json)
    except ValueError:
        return VerifyResult("malformed_envelope", None, "json_decode_failed")
    if not isinstance(claims, dict):
        return VerifyResult("malformed_envelope", None, "claims_not_dict")
    if set(claims.keys()) != set(TOKEN_CLAIM_KEYS):
        return VerifyResult("malformed_envelope", None, "claim_keys_mismatch")

    # Intent must be in the closed vocab.
    intent = claims.get("intent")
    if intent not in TOKEN_INTENTS:
        return VerifyResult("intent_unknown", None, "intent_not_in_vocab")

    # Kid lookup.
    kid = claims.get("kid")
    if not isinstance(kid, str) or kid not in secrets_by_kid:
        return VerifyResult("unknown_kid", None, "kid_not_in_secrets_map")
    secret = secrets_by_kid[kid]
    try:
        _validate_secret(secret)
    except (TypeError, ValueError):
        return VerifyResult("signature_invalid", None, "secret_invalid_shape")

    # Signature.
    expected_sig = _sign(claims, secret=secret)
    if not hmac.compare_digest(expected_sig, sig):
        return VerifyResult("signature_invalid", None, "hmac_mismatch")

    # Bindings.
    if claims.get("event_id") != expected_event_id:
        return VerifyResult("binding_mismatch", None, "event_id_mismatch")
    if claims.get("pr_number") != expected_pr_number:
        return VerifyResult("binding_mismatch", None, "pr_number_mismatch")
    if claims.get("pr_head_sha") != expected_pr_head_sha:
        return VerifyResult("binding_mismatch", None, "pr_head_sha_mismatch")
    if claims.get("evidence_hash") != expected_evidence_hash:
        return VerifyResult("binding_mismatch", None, "evidence_hash_mismatch")
    if claims.get("release_tag") != expected_release_tag:
        return VerifyResult("binding_mismatch", None, "release_tag_mismatch")

    # Replay protection.
    if seen_nonces is not None:
        nonce = claims.get("nonce")
        if isinstance(nonce, str) and nonce in seen_nonces:
            return VerifyResult("replay_detected", None, "nonce_seen")

    # Expiry.
    now_ts = now if now is not None else _utcnow()
    exp_raw = claims.get("expires_at_utc")
    if not isinstance(exp_raw, str):
        return VerifyResult("malformed_envelope", None, "expires_at_utc_not_str")
    try:
        norm = exp_raw.replace("Z", "+00:00")
        exp = datetime.fromisoformat(norm)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
    except ValueError:
        return VerifyResult("malformed_envelope", None, "expires_at_utc_unparseable")
    if now_ts >= exp:
        return VerifyResult("expired", None, "now_at_or_after_expiry")

    return VerifyResult("ok", dict(claims), "verified")


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "HMAC_ALGORITHM",
    "MAX_TTL_SECONDS",
    "MIN_SECRET_LENGTH_BYTES",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "TOKEN_CLAIM_KEYS",
    "TOKEN_INTENTS",
    "VERIFY_OUTCOMES",
    "VerifyResult",
    "mint_token",
    "step5_implementation_allowed",
    "verify_token",
]
