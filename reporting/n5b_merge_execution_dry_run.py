"""N5b Phase 2 — Dry-run audit projector (B2.8c, preflight only).

Sentinel-restricted writer for the closed-schema **preflight**
artefact emitted by the N5b Phase 2 token-bound dry-run endpoint
skeleton + walker
(``dashboard/api_merge_execution_dry_run.py``).

Scope of this slice (B2.8c) is the preflight artefact ONLY, per
``docs/governance/n5b_phase2_implementation_plan.md`` §6.2:

    "The preflight artefact is written before the verify call."

…with the operator-mandated B2.8c correction that the preflight
write is only performed AFTER the body / N4b / N4c / token-binding
preconditions 1–7 all pass — never on invalid, replayed,
binding-mismatched, expired, or malformed token inputs.

The dry-run-decision artefact (``logs/n5b_merge_execution/dry_run/latest.json``),
the dry-run history artefact (``…/dry_run/history.jsonl``), and the
failure artefact (``…/failure/<cycle_id>.json``) are NOT written
by this slice. They are reserved for B2.8d / B2.8e per the
implementation plan §2.6.

Hard guarantees (pinned by
``tests/unit/test_n5b_merge_execution_dry_run.py``):

* Stdlib + :func:`reporting.agent_audit_summary.assert_no_secrets`
  (read-only redactor guard). No other imports.
* No subprocess, no socket, no urllib, no requests, no httpx, no
  aiohttp, no asyncio.
* No GitHub CLI literal, no version-control CLI literal, no
  branch-protection-bypass admin flag, no PR-mutation attribute
  name literal.
* No environment-variable read (the projector takes every value as
  an argument from the caller; the caller alone — via
  ``reporting.approval_token_runtime`` — is allowed to read the env
  HMAC secret).
* Atomic write via ``tempfile.mkstemp`` + ``os.replace``.
* Sentinel-restricted write prefix: any write whose absolute path
  does not contain ``logs/n5b_merge_execution/`` raises
  ``ValueError`` BEFORE the temp file is created.
* :func:`reporting.agent_audit_summary.assert_no_secrets` runs on
  the snapshot before write; a credential-shaped string aborts
  with ``AssertionError`` and no file is created.
* Closed snapshot schema (key-set check) — drift fails the pin
  test in the same PR that introduces the change.
* The closed ``discipline_invariants`` dict is emitted into every
  artefact, mirroring the ``api_merge_preflight`` envelope contract.
* :data:`step5_implementation_allowed` is ``Final[False]``,
  :data:`STEP5_ENABLED_SUBSTAGE` is ``Final["none"]``,
  ``level6_enabled`` is always ``False``.
* The projector never accepts the raw nonce or the raw token —
  only the caller-supplied ``token_kid`` (verified) and
  ``nonce_hash`` (sha256 hex of the verified nonce). The closed
  schema does not contain a ``token`` field or a raw ``nonce``
  field.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.projector"
REPORT_KIND: Final[str] = "n5b_preflight"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed write-prefix + repo-relative artefact paths
# ---------------------------------------------------------------------------

#: Sentinel substring that EVERY write path must contain. The
#: :func:`_atomic_write_json` helper raises ``ValueError`` if the
#: target path does not match. Defense-in-depth against a future
#: caller that mistakenly passes a non-N5b log path.
WRITE_PREFIX: Final[str] = "logs/n5b_merge_execution/"

PREFLIGHT_DIR: Final[Path] = REPO_ROOT / "logs" / "n5b_merge_execution" / "preflight"
PREFLIGHT_LATEST: Final[Path] = PREFLIGHT_DIR / "latest.json"
PREFLIGHT_LATEST_RELATIVE: Final[str] = (
    "logs/n5b_merge_execution/preflight/latest.json"
)


# ---------------------------------------------------------------------------
# Closed allowed values
# ---------------------------------------------------------------------------

#: The ONLY base ref the N5b adapter accepts (parent doc §3 row 12).
PR_BASE_REF: Final[str] = "main"

#: The pinned dry-run intent literal.
DRY_RUN_INTENT: Final[str] = "mobile_approval_dispatch"

#: The closed operator_actor vocabulary. The B2.8c walker is
#: session-protected, so it always passes ``"session"``. A future
#: operator-token-mediated path would pass ``"operator_token"``.
OPERATOR_ACTORS: Final[tuple[str, ...]] = ("session", "operator_token")


# ---------------------------------------------------------------------------
# Discipline invariants — mirrored into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "dry_run_only": True,
    "live_merge_implemented": False,
    "executes_merge": False,
    "calls_github_api": False,
    "uses_subprocess_or_network": False,
    "deploy_coupled": False,
    "mints_or_verifies_approval_tokens": False,
    "writes_seed_files": False,
    "writes_generated_seed": False,
    "opens_or_merges_prs": False,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
    "level6_enabled": False,
}


# ---------------------------------------------------------------------------
# Closed preflight snapshot schema (exact key set)
# ---------------------------------------------------------------------------

PREFLIGHT_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "report_kind",
    "module_version",
    "pr_number",
    "pr_head_sha",
    "pr_base_ref",
    "intent",
    "token_kid",
    "nonce_hash",
    "operator_actor",
    "generated_at_utc",
    "step5_implementation_allowed",
    "step5_enabled_substage",
    "level6_enabled",
    "dry_run_only",
    "live_merge_implemented",
    "deploy_coupled",
    "discipline_invariants",
)


# ---------------------------------------------------------------------------
# Snapshot builder (pure, deterministic — no I/O)
# ---------------------------------------------------------------------------


def build_preflight_snapshot(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the closed-schema preflight snapshot dict.

    Pure — no I/O. The caller is responsible for supplying VERIFIED
    values for ``token_kid`` and ``nonce_hash`` (sha256 hex of the
    nonce, NOT the raw nonce). The projector enforces value-shape
    invariants and rejects out-of-vocab ``operator_actor`` values
    so the artefact never carries an unanchored sentinel.

    Raises:
      :class:`TypeError` if ``pr_number`` is not an ``int`` (or is a
      ``bool``).
      :class:`ValueError` if any string field fails its bounded-shape
      check, or if ``operator_actor`` is outside
      :data:`OPERATOR_ACTORS`.
    """
    if not isinstance(pr_number, int) or isinstance(pr_number, bool):
        raise TypeError("pr_number must be int")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")
    if not isinstance(pr_head_sha, str) or not pr_head_sha:
        raise ValueError("pr_head_sha must be a non-empty string")
    if len(pr_head_sha) > 64:
        raise ValueError("pr_head_sha exceeds 64 chars")
    if not isinstance(token_kid, str) or not token_kid:
        raise ValueError("token_kid must be a non-empty string")
    if len(token_kid) > 64:
        raise ValueError("token_kid exceeds 64 chars")
    if not isinstance(nonce_hash, str) or len(nonce_hash) != 64:
        raise ValueError("nonce_hash must be a 64-char sha256 hex digest")
    if any(c not in "0123456789abcdef" for c in nonce_hash):
        raise ValueError("nonce_hash must be lowercase hex")
    if operator_actor not in OPERATOR_ACTORS:
        raise ValueError(
            f"operator_actor must be one of {OPERATOR_ACTORS}; got {operator_actor!r}"
        )
    if not isinstance(generated_at_utc, str) or not generated_at_utc:
        raise ValueError("generated_at_utc must be a non-empty ISO 8601 string")

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "pr_base_ref": PR_BASE_REF,
        "intent": DRY_RUN_INTENT,
        "token_kid": token_kid,
        "nonce_hash": nonce_hash,
        "operator_actor": operator_actor,
        "generated_at_utc": generated_at_utc,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "level6_enabled": False,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    assert set(snapshot.keys()) == set(PREFLIGHT_SNAPSHOT_KEYS), (
        f"preflight snapshot key drift: {sorted(snapshot.keys())!r} vs "
        f"{sorted(PREFLIGHT_SNAPSHOT_KEYS)!r}"
    )
    return snapshot


# ---------------------------------------------------------------------------
# Sentinel-restricted atomic writer
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` atomically.

    Sentinel-restricted: ``path`` MUST contain
    :data:`WRITE_PREFIX` in its POSIX-form string. Otherwise raises
    ``ValueError`` BEFORE the temp file is created.

    ``assert_no_secrets`` is invoked on ``payload`` first. A
    credential-shaped string aborts the write with
    ``AssertionError``.
    """
    posix = path.as_posix()
    if WRITE_PREFIX not in posix:
        raise ValueError(
            "n5b_merge_execution_dry_run._atomic_write_json refuses "
            f"non-N5b-logs output path: {path}"
        )
    assert_no_secrets(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".n5b_merge_execution_dry_run.",
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


# ---------------------------------------------------------------------------
# Public writer — preflight only (B2.8c scope)
# ---------------------------------------------------------------------------


def write_preflight(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    generated_at_utc: str,
    target_path: Path | None = None,
) -> Path:
    """Build + persist the closed-schema preflight artefact.

    Writes to :data:`PREFLIGHT_LATEST` by default. ``target_path``
    is exposed for unit-test isolation (the test redirects writes
    into ``tmp_path/logs/n5b_merge_execution/preflight/latest.json``);
    even the test path must contain :data:`WRITE_PREFIX` or the
    sentinel guard fails.

    The dry-run-decision artefact, the dry-run history artefact,
    and the failure artefact are NOT written by this function.
    Those writers are reserved for B2.8d / B2.8e per the
    implementation plan §2.6.
    """
    snapshot = build_preflight_snapshot(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
        operator_actor=operator_actor,
        generated_at_utc=generated_at_utc,
    )
    target = target_path if target_path is not None else PREFLIGHT_LATEST
    _atomic_write_json(target, snapshot)
    return target


__all__ = [
    "DRY_RUN_INTENT",
    "MODULE_VERSION",
    "OPERATOR_ACTORS",
    "PREFLIGHT_DIR",
    "PREFLIGHT_LATEST",
    "PREFLIGHT_LATEST_RELATIVE",
    "PREFLIGHT_SNAPSHOT_KEYS",
    "PR_BASE_REF",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "WRITE_PREFIX",
    "build_preflight_snapshot",
    "step5_implementation_allowed",
    "write_preflight",
]
