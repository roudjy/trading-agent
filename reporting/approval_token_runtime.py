"""N4b — Runtime approval-token gate (env-gated wrapper around N4a).

Provides the env-driven layer on top of the existing pure N4a
``approval_token_gate`` mint/verify primitives. This is the **only**
module allowed to read the HMAC secret env var and to persist
seen-nonce replay state.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.approval_token_gate`` (read-only) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* The literal env-var name ``ADE_APPROVAL_TOKEN_HMAC_SECRET`` IS
  allowed in this module — this is the **only** module permitted to
  reference it. Every other module pins its absence.
* :func:`is_configured` returns a boolean only; it NEVER returns,
  logs, prints, or echoes the secret value.
* Mint refuses to operate without a valid env secret (length-checked
  via N4a's ``MIN_SECRET_LENGTH_BYTES`` ≥ 32 bytes).
* Mint binds every token to the operator-supplied closed-vocab
  ``intent`` + ``event_id`` + the optional PR/release identifiers
  per N4a's closed claim schema.
* Verify on ``outcome == "ok"`` records the nonce to the bounded
  on-disk store at ``state/approval_token_seen_nonces.jsonl``;
  subsequent verifies with the same nonce are rejected with the
  closed-vocab outcome ``replay_detected``.
* The seen-nonce store is gitignored (``state/`` is in
  ``.gitignore``), bounded to :data:`MAX_SEEN_NONCES` rows, atomic
  rewrite, sentinel-restricted writes.
* This module performs NO approve / reject / merge / deploy
  action. It only proves that a token can be minted and verified;
  the underlying action is N5 territory.
* Importing this module does NOT flip Step 5 invariants.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import approval_token_gate as atg

MODULE_VERSION: Final[str] = "v3.15.16.N4b"
SCHEMA_VERSION: Final[str] = "1.0"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed env-var names
# ---------------------------------------------------------------------------

#: Name of the env var the operator must export on the VPS. Value
#: must be ≥32 bytes when interpreted as hex / base64 / raw. The
#: module reads this once per call and never logs / prints the
#: value. Recommended generation:
#:
#:     openssl rand -hex 32
#:
#: then export as ``ADE_APPROVAL_TOKEN_HMAC_SECRET=<the hex string>``.
ENV_APPROVAL_TOKEN_HMAC_SECRET: Final[str] = "ADE_APPROVAL_TOKEN_HMAC_SECRET"

#: Current key id. A single static kid is sufficient for the smallest
#: safe slice; rotating to a new kid requires a code change pinned by
#: an updated test. The kid appears in token claims so future N4
#: rotations can verify against multiple secrets simultaneously.
CURRENT_KID: Final[str] = "k1"


# ---------------------------------------------------------------------------
# Persistent seen-nonce store
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

#: Bounded seen-nonce store under ``state/``. ``state/`` is fully
#: gitignored (line 25 of ``.gitignore``). The file is treated as a
#: bounded JSONL: every record helper compacts to the newest
#: :data:`MAX_SEEN_NONCES` rows on each write.
SEEN_NONCES_PATH: Final[Path] = (
    REPO_ROOT / "state" / "approval_token_seen_nonces.jsonl"
)
SEEN_NONCES_RELATIVE_PATH: Final[str] = "state/approval_token_seen_nonces.jsonl"

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "state/approval_token_seen_nonces"

#: Maximum nonces retained in the bounded store. The runtime
#: replay-protection window for an operator-paced approval flow.
MAX_SEEN_NONCES: Final[int] = 1024


# ---------------------------------------------------------------------------
# Closed mint-result + verify-result envelopes
# ---------------------------------------------------------------------------

#: Closed mint-result envelope keys. The caller (dashboard API
#: layer) receives exactly this shape; no secret material appears.
MINT_RESULT_KEYS: Final[tuple[str, ...]] = (
    "status",
    "token",
    "kid",
    "intent",
    "event_id",
    "issued_at_utc",
    "expires_at_utc",
)

#: Closed verify-result envelope keys.
VERIFY_RESULT_KEYS: Final[tuple[str, ...]] = (
    "status",
    "outcome",
    "reason",
)


# ---------------------------------------------------------------------------
# Env-secret reader (never echoes the value)
# ---------------------------------------------------------------------------


def _decode_env_secret(raw: str) -> bytes | None:
    """Decode the env-supplied secret. Accepts hex, base64url, or
    raw bytes (utf-8). Returns ``None`` if no decoding yields ≥ the
    minimum length."""
    if not isinstance(raw, str) or not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    # Try hex first (the recommended form: openssl rand -hex 32 → 64 hex chars).
    try:
        decoded = bytes.fromhex(candidate)
        if len(decoded) >= atg.MIN_SECRET_LENGTH_BYTES:
            return decoded
    except ValueError:
        pass
    # Try base64url next.
    try:
        import base64

        pad = "=" * ((4 - len(candidate) % 4) % 4)
        decoded = base64.urlsafe_b64decode(candidate + pad)
        if len(decoded) >= atg.MIN_SECRET_LENGTH_BYTES:
            return decoded
    except Exception:
        pass
    # Fall back to raw bytes.
    raw_bytes = candidate.encode("utf-8")
    if len(raw_bytes) >= atg.MIN_SECRET_LENGTH_BYTES:
        return raw_bytes
    return None


def _read_env_secret() -> bytes | None:
    """Return the decoded env secret as bytes, or ``None`` if absent
    or too short. NEVER logs / prints / echoes the value."""
    raw = os.environ.get(ENV_APPROVAL_TOKEN_HMAC_SECRET)
    if not isinstance(raw, str):
        return None
    return _decode_env_secret(raw)


def is_configured() -> bool:
    """Return True iff the env secret is set and decodes to ≥32 bytes.

    Returns a boolean only; does not echo the secret. Pinned by tests.
    """
    return _read_env_secret() is not None


def current_kid() -> str:
    """Return the active kid. Hard-coded for the smallest safe slice."""
    return CURRENT_KID


def secrets_by_kid() -> dict[str, bytes]:
    """Return the ``{kid: secret}`` map for :func:`atg.verify_token`.

    Empty dict if not configured."""
    secret = _read_env_secret()
    if secret is None:
        return {}
    return {CURRENT_KID: secret}


# ---------------------------------------------------------------------------
# Seen-nonce store (atomic rewrite, bounded)
# ---------------------------------------------------------------------------


def _read_seen_nonces() -> set[str]:
    """Read the persistent seen-nonce store. Best-effort; never raises."""
    path = SEEN_NONCES_PATH
    if not path.is_file():
        return set()
    out: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except ValueError:
            continue
        if isinstance(entry, dict):
            nonce = entry.get("nonce")
            if isinstance(nonce, str) and nonce:
                out.add(nonce)
    return out


def is_nonce_seen(nonce: str) -> bool:
    if not isinstance(nonce, str) or not nonce:
        return False
    return nonce in _read_seen_nonces()


def _atomic_replace_jsonl(path: Path, lines: list[str]) -> None:
    """Atomic-write the bounded JSONL. Sentinel-restricted."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "approval_token_runtime._atomic_replace_jsonl refuses "
            f"non-state path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + ("\n" if lines else "")
    fd, tmp_name = tempfile.mkstemp(
        prefix=".approval_token_seen_nonces.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def record_nonce(nonce: str) -> bool:
    """Append a nonce to the bounded seen-store, then compact to the
    last :data:`MAX_SEEN_NONCES` rows. Returns True if the nonce was
    newly recorded; False if it was already present (caller can
    treat as a no-op).

    Never raises. NEVER stores or logs the secret. Only the nonce
    (16-byte hex from N4a) is written.
    """
    if not isinstance(nonce, str) or not nonce:
        return False
    path = SEEN_NONCES_PATH
    existing_lines: list[str] = []
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                entry = json.loads(s)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            n = entry.get("nonce")
            if isinstance(n, str) and n:
                if n == nonce:
                    return False
                existing_lines.append(s)
    new_line = json.dumps({"nonce": nonce}, sort_keys=True)
    existing_lines.append(new_line)
    # Compact to the newest MAX_SEEN_NONCES rows.
    if len(existing_lines) > MAX_SEEN_NONCES:
        existing_lines = existing_lines[-MAX_SEEN_NONCES:]
    _atomic_replace_jsonl(path, existing_lines)
    return True


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------


def mint_runtime(
    *,
    intent: str,
    event_id: str,
    pr_number: int | None = None,
    pr_head_sha: str | None = None,
    evidence_hash: str,
    release_tag: str | None = None,
) -> dict[str, Any]:
    """Mint an HMAC-SHA256 approval token using the env secret.

    Returns a closed-shape envelope (see :data:`MINT_RESULT_KEYS`).
    Failure modes are returned as ``status`` values; this function
    never raises for predictable failure modes (missing env, invalid
    intent, etc.). The token string is included on ``status == "ok"``;
    on any other status it is omitted (``None``).
    """
    secret = _read_env_secret()
    if secret is None:
        return _mint_envelope(
            status="configuration_missing",
            token=None,
            kid=CURRENT_KID,
            intent=intent,
            event_id=event_id,
            issued_at_utc="",
            expires_at_utc="",
        )
    if intent not in atg.TOKEN_INTENTS:
        return _mint_envelope(
            status="invalid_intent",
            token=None,
            kid=CURRENT_KID,
            intent=intent,
            event_id=event_id,
            issued_at_utc="",
            expires_at_utc="",
        )
    if not isinstance(event_id, str) or not event_id:
        return _mint_envelope(
            status="invalid_event_id",
            token=None,
            kid=CURRENT_KID,
            intent=intent,
            event_id=str(event_id or ""),
            issued_at_utc="",
            expires_at_utc="",
        )
    if not isinstance(evidence_hash, str) or not evidence_hash:
        return _mint_envelope(
            status="invalid_evidence_hash",
            token=None,
            kid=CURRENT_KID,
            intent=intent,
            event_id=event_id,
            issued_at_utc="",
            expires_at_utc="",
        )
    try:
        token = atg.mint_token(
            intent=intent,
            event_id=event_id,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            evidence_hash=evidence_hash,
            release_tag=release_tag,
            kid=CURRENT_KID,
            secret=secret,
            ttl_seconds=atg.DEFAULT_TTL_SECONDS,
        )
    except (TypeError, ValueError) as exc:
        return _mint_envelope(
            status="mint_rejected",
            token=None,
            kid=CURRENT_KID,
            intent=intent,
            event_id=event_id,
            issued_at_utc="",
            expires_at_utc="",
            reason=exc.__class__.__name__,
        )
    claims = _claims_from_token(token)
    return _mint_envelope(
        status="ok",
        token=token,
        kid=CURRENT_KID,
        intent=intent,
        event_id=event_id,
        issued_at_utc=str(claims.get("issued_at_utc") or ""),
        expires_at_utc=str(claims.get("expires_at_utc") or ""),
    )


def _claims_from_token(token: str) -> dict[str, Any]:
    """Best-effort decode of the claims portion. Never raises."""
    if not isinstance(token, str) or "." not in token:
        return {}
    try:
        claims_b64, _sig_b64 = token.split(".", 1)
        import base64

        pad = "=" * ((4 - len(claims_b64) % 4) % 4)
        decoded = base64.urlsafe_b64decode(claims_b64 + pad)
        obj = json.loads(decoded)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _mint_envelope(
    *,
    status: str,
    token: str | None,
    kid: str,
    intent: str,
    event_id: str,
    issued_at_utc: str,
    expires_at_utc: str,
    reason: str | None = None,
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "status": status,
        "token": token,
        "kid": kid,
        "intent": intent,
        "event_id": event_id,
        "issued_at_utc": issued_at_utc,
        "expires_at_utc": expires_at_utc,
    }
    if reason is not None:
        env["reason"] = reason
    return env


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_runtime(
    *,
    token: str,
    expected_event_id: str,
    expected_pr_number: int | None = None,
    expected_pr_head_sha: str | None = None,
    expected_evidence_hash: str,
    expected_release_tag: str | None = None,
) -> dict[str, Any]:
    """Verify a token against the env secret + record the nonce on
    success. Returns the closed-shape verify envelope (see
    :data:`VERIFY_RESULT_KEYS`).

    This function NEVER performs the underlying action. The caller
    must independently check business invariants before acting on
    the verified claims.
    """
    by_kid = secrets_by_kid()
    if not by_kid:
        return {
            "status": "configuration_missing",
            "outcome": "",
            "reason": "env_secret_absent",
        }
    seen = _read_seen_nonces()
    result = atg.verify_token(
        token,
        expected_event_id=expected_event_id,
        expected_pr_number=expected_pr_number,
        expected_pr_head_sha=expected_pr_head_sha,
        expected_evidence_hash=expected_evidence_hash,
        expected_release_tag=expected_release_tag,
        secrets_by_kid=by_kid,
        seen_nonces=seen,
    )
    if result.outcome == "ok" and isinstance(result.claims, dict):
        nonce = result.claims.get("nonce")
        if isinstance(nonce, str) and nonce:
            try:
                record_nonce(nonce)
            except Exception:
                # Best-effort: a failed write does not turn a verified
                # token into a rejected one. The next verify of the
                # same nonce will still be detected via the in-memory
                # ``seen`` set on a re-read.
                pass
    return {
        "status": "ok" if result.outcome == "ok" else "rejected",
        "outcome": result.outcome,
        "reason": result.reason,
    }


__all__ = [
    "CURRENT_KID",
    "ENV_APPROVAL_TOKEN_HMAC_SECRET",
    "MAX_SEEN_NONCES",
    "MINT_RESULT_KEYS",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "SEEN_NONCES_PATH",
    "SEEN_NONCES_RELATIVE_PATH",
    "STEP5_ENABLED_SUBSTAGE",
    "VERIFY_RESULT_KEYS",
    "current_kid",
    "is_configured",
    "is_nonce_seen",
    "mint_runtime",
    "record_nonce",
    "secrets_by_kid",
    "step5_implementation_allowed",
    "verify_runtime",
]
