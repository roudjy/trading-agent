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
MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.projector_implemented"
REPORT_KIND: Final[str] = "n5b_preflight"
FAILURE_REPORT_KIND: Final[str] = "n5b_failure"
DRY_RUN_REPORT_KIND: Final[str] = "n5b_dry_run"


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

#: B2.8d failure artefact directory. Per parent-doc §6 / §2.6, each
#: §7 stop condition the walker emits writes a failure artefact at
#: ``logs/n5b_merge_execution/failure/<cycle_id>.json`` with the
#: closed schema below and a redacted ``stop_reason``. No raw nonce,
#: no raw token, no PR diff content.
FAILURE_DIR: Final[Path] = REPO_ROOT / "logs" / "n5b_merge_execution" / "failure"
FAILURE_DIR_RELATIVE: Final[str] = "logs/n5b_merge_execution/failure/"

#: B2.8e dry-run artefact paths. Per parent-doc §2.6, every dry-run
#: invocation that produces a decision (``ok`` or ``rejected``)
#: writes the closed-schema dry-run snapshot to
#: ``dry_run/latest.json`` and appends the same row to
#: ``dry_run/history.jsonl`` (append-only, bounded by
#: :data:`MAX_HISTORY_ROWS`). No raw token, no raw nonce.
DRY_RUN_DIR: Final[Path] = REPO_ROOT / "logs" / "n5b_merge_execution" / "dry_run"
DRY_RUN_LATEST: Final[Path] = DRY_RUN_DIR / "latest.json"
DRY_RUN_LATEST_RELATIVE: Final[str] = (
    "logs/n5b_merge_execution/dry_run/latest.json"
)
DRY_RUN_HISTORY: Final[Path] = DRY_RUN_DIR / "history.jsonl"
DRY_RUN_HISTORY_RELATIVE: Final[str] = (
    "logs/n5b_merge_execution/dry_run/history.jsonl"
)

#: Bounded history-row retention. Each append compacts to the newest
#: :data:`MAX_HISTORY_ROWS` rows so the file size stays bounded.
MAX_HISTORY_ROWS: Final[int] = 1024


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
# Closed §7 stop-condition vocabulary the B2.8d walker is permitted
# to emit. Mirrors the parent-doc
# ``docs/governance/n5b_merge_execution_plan.md`` §7 enumeration
# narrowed to the §6.3 list for B2.8d. The walker writes one of
# these values into the failure artefact's ``stop_condition`` field.
# New literals must NOT be added without a doc update.
# ---------------------------------------------------------------------------

B2_8D_STOP_CONDITIONS: Final[tuple[str, ...]] = (
    # Token-side (also emitted by B2.8c walker for 1–7; included
    # here so the failure artefact's schema validator accepts them).
    "token_missing",
    "token_invalid",
    "replay_detected",
    "binding_mismatch",
    "pr_number_mismatch",
    # B2.8d additions for preconditions 8–17 (closed per §6.3).
    "head_sha_mismatch",
    "merge_state_not_clean",
    "checks_not_green",
    "branch_protection_not_satisfied",
    "unexpected_files_touched",
    "deploy_coupling_detected",
    "step5_flag_changed",
    "level_6_attempted",
    "protected_path_violation",
    "stale_recommendation",
    "network_uncertain",
    "audit_write_failure",
)

#: Maximum bounded length of the failure ``stop_reason`` field.
#: Defense-in-depth against arbitrary upstream-provided strings
#: leaking secret-shaped material.
MAX_STOP_REASON_LEN: Final[int] = 200


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


# ---------------------------------------------------------------------------
# B2.8d failure artefact — closed schema
# ---------------------------------------------------------------------------


FAILURE_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "report_kind",
    "module_version",
    "cycle_id",
    "pr_number",
    "pr_head_sha",
    "pr_base_ref",
    "intent",
    "stop_condition",
    "stop_reason",
    "preconditions_evaluated",
    "preconditions_passed",
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


def _validate_cycle_id(cycle_id: str) -> None:
    """``cycle_id`` is used as a filename segment, so it must be
    charset-restricted to safe ASCII (alphanumeric + underscore +
    hyphen). Any other character raises ``ValueError``."""
    if not isinstance(cycle_id, str) or not cycle_id:
        raise ValueError("cycle_id must be a non-empty string")
    if len(cycle_id) > 128:
        raise ValueError("cycle_id exceeds 128 chars")
    for ch in cycle_id:
        if not (ch.isalnum() or ch in ("_", "-")):
            raise ValueError(
                f"cycle_id contains unsafe character: {ch!r}"
            )


def build_failure_snapshot(
    *,
    cycle_id: str,
    pr_number: int,
    pr_head_sha: str,
    stop_condition: str,
    stop_reason: str,
    preconditions_evaluated: int,
    preconditions_passed: int,
    operator_actor: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the closed-schema failure snapshot dict.

    Pure — no I/O. Caller is responsible for supplying a
    ``stop_condition`` from :data:`B2_8D_STOP_CONDITIONS` and a
    ``stop_reason`` that has been bounded / redacted at the caller
    side. The projector additionally truncates ``stop_reason`` to
    :data:`MAX_STOP_REASON_LEN` chars defense-in-depth.

    Raises:
      :class:`TypeError` if ``pr_number`` /
      ``preconditions_evaluated`` / ``preconditions_passed`` are not
      ``int`` (or are ``bool``).
      :class:`ValueError` for any string-shape or vocabulary failure.
    """
    _validate_cycle_id(cycle_id)
    if not isinstance(pr_number, int) or isinstance(pr_number, bool):
        raise TypeError("pr_number must be int")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")
    if not isinstance(pr_head_sha, str) or not pr_head_sha:
        raise ValueError("pr_head_sha must be a non-empty string")
    if len(pr_head_sha) > 64:
        raise ValueError("pr_head_sha exceeds 64 chars")
    if stop_condition not in B2_8D_STOP_CONDITIONS:
        raise ValueError(
            f"stop_condition must be one of {B2_8D_STOP_CONDITIONS}; "
            f"got {stop_condition!r}"
        )
    if not isinstance(stop_reason, str):
        raise TypeError("stop_reason must be str")
    if not isinstance(preconditions_evaluated, int) or isinstance(
        preconditions_evaluated, bool
    ):
        raise TypeError("preconditions_evaluated must be int")
    if not isinstance(preconditions_passed, int) or isinstance(
        preconditions_passed, bool
    ):
        raise TypeError("preconditions_passed must be int")
    if preconditions_evaluated < 0 or preconditions_passed < 0:
        raise ValueError(
            "preconditions_evaluated / preconditions_passed must be non-negative"
        )
    if preconditions_passed > preconditions_evaluated:
        raise ValueError(
            "preconditions_passed must not exceed preconditions_evaluated"
        )
    if operator_actor not in OPERATOR_ACTORS:
        raise ValueError(
            f"operator_actor must be one of {OPERATOR_ACTORS}; got {operator_actor!r}"
        )
    if not isinstance(generated_at_utc, str) or not generated_at_utc:
        raise ValueError("generated_at_utc must be a non-empty ISO 8601 string")

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": FAILURE_REPORT_KIND,
        "module_version": MODULE_VERSION,
        "cycle_id": cycle_id,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "pr_base_ref": PR_BASE_REF,
        "intent": DRY_RUN_INTENT,
        "stop_condition": stop_condition,
        "stop_reason": stop_reason[:MAX_STOP_REASON_LEN],
        "preconditions_evaluated": preconditions_evaluated,
        "preconditions_passed": preconditions_passed,
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
    assert set(snapshot.keys()) == set(FAILURE_SNAPSHOT_KEYS), (
        f"failure snapshot key drift: {sorted(snapshot.keys())!r} vs "
        f"{sorted(FAILURE_SNAPSHOT_KEYS)!r}"
    )
    return snapshot


def write_failure(
    *,
    cycle_id: str,
    pr_number: int,
    pr_head_sha: str,
    stop_condition: str,
    stop_reason: str,
    preconditions_evaluated: int,
    preconditions_passed: int,
    operator_actor: str,
    generated_at_utc: str,
    target_path: Path | None = None,
) -> Path:
    """Build + persist the closed-schema failure artefact.

    Writes to ``FAILURE_DIR / f"{cycle_id}.json"`` by default.
    ``target_path`` is exposed for unit-test isolation; even the
    test path must contain :data:`WRITE_PREFIX` or the sentinel
    guard raises ``ValueError``.

    The dry-run-decision artefact and the dry-run history artefact
    are NOT written by this function. Those writers remain
    reserved for B2.8e per the implementation plan §2.6.
    """
    snapshot = build_failure_snapshot(
        cycle_id=cycle_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        stop_condition=stop_condition,
        stop_reason=stop_reason,
        preconditions_evaluated=preconditions_evaluated,
        preconditions_passed=preconditions_passed,
        operator_actor=operator_actor,
        generated_at_utc=generated_at_utc,
    )
    target = (
        target_path if target_path is not None else FAILURE_DIR / f"{cycle_id}.json"
    )
    _atomic_write_json(target, snapshot)
    return target


# ---------------------------------------------------------------------------
# B2.8e dry-run artefact — closed schema + granularity sentinels
# ---------------------------------------------------------------------------


#: Closed enumeration of the ``required_checks_granularity`` values
#: the projector recognises. ``rollup_only`` indicates the upstream
#: A22 artefact provides a single rollup (``SUCCESS`` / ``PASSED`` /
#: …) rather than per-required-check conclusions. A future upstream
#: extension can append ``per_check`` without weakening this list;
#: tests pin the closed set.
REQUIRED_CHECKS_GRANULARITY_VALUES: Final[tuple[str, ...]] = ("rollup_only",)

#: Closed enumeration of the ``protected_path_granularity`` values.
#: ``boolean_only`` indicates the upstream ``github_pr_lifecycle``
#: artefact exposes only a single ``protected_paths_touched`` flag
#: rather than the list of file paths that triggered it. A future
#: upstream extension can append ``per_file`` without weakening
#: this list.
PROTECTED_PATH_GRANULARITY_VALUES: Final[tuple[str, ...]] = ("boolean_only",)

#: Number of §3 preconditions tracked in the dry-run ``preconditions``
#: dict (one boolean per §3 row).
DRY_RUN_PRECONDITION_COUNT: Final[int] = 17

#: Closed keys for the dry-run ``preconditions`` boolean dict.
DRY_RUN_PRECONDITION_KEYS: Final[tuple[str, ...]] = tuple(
    f"precondition_{i}" for i in range(1, DRY_RUN_PRECONDITION_COUNT + 1)
)


DRY_RUN_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
    # All preflight fields (closed)
    "schema_version",
    "report_kind",                    # "n5b_dry_run"
    "module_version",
    "pr_number",
    "pr_head_sha",
    "pr_base_ref",                    # "main"
    "intent",                         # "mobile_approval_dispatch"
    "token_kid",
    "nonce_hash",
    "operator_actor",                 # "session" | "operator_token"
    "generated_at_utc",
    # §6.2 dry-run additions
    "preconditions",                  # dict[str, bool] — DRY_RUN_PRECONDITION_KEYS
    "recommendation_action_seen",     # str from N5a row (or "" if unread)
    "recommendation_reason_seen",     # str from N5a row (or "" if unread)
    "merge_state_status_seen",        # str from A22 row (or "" if unread)
    "required_checks_summary",        # dict[str, str] — {"_rollup": <rollup>}
    "required_checks_granularity",    # str — REQUIRED_CHECKS_GRANULARITY_VALUES
    "protected_path_violations",      # list[str] — empty for B2.8e
    "protected_path_granularity",     # str — PROTECTED_PATH_GRANULARITY_VALUES
    "would_proceed",                  # bool — True iff status="ok"
    "stop_condition",                 # str | null — null when would_proceed=True
    # Discipline invariants
    "step5_implementation_allowed",   # False
    "step5_enabled_substage",         # "none"
    "level6_enabled",                 # False
    "dry_run_only",                   # True
    "live_merge_implemented",         # False
    "deploy_coupled",                 # False
    "discipline_invariants",          # closed dict
)


def _validate_preconditions_dict(value: Any) -> None:
    if not isinstance(value, dict):
        raise TypeError("preconditions must be a dict")
    if set(value.keys()) != set(DRY_RUN_PRECONDITION_KEYS):
        raise ValueError(
            "preconditions keys must equal "
            f"{sorted(DRY_RUN_PRECONDITION_KEYS)!r}; "
            f"got {sorted(value.keys())!r}"
        )
    for k, v in value.items():
        if not isinstance(v, bool):
            raise TypeError(f"preconditions[{k!r}] must be bool")


def _validate_required_checks_summary(value: Any) -> None:
    if not isinstance(value, dict):
        raise TypeError("required_checks_summary must be a dict")
    if not value:
        raise ValueError("required_checks_summary must not be empty")
    for k, v in value.items():
        if not isinstance(k, str) or not k:
            raise ValueError("required_checks_summary keys must be non-empty str")
        if not isinstance(v, str):
            raise TypeError("required_checks_summary values must be str")


def _validate_protected_path_violations(value: Any) -> None:
    if not isinstance(value, list):
        raise TypeError("protected_path_violations must be a list")
    for entry in value:
        if not isinstance(entry, str):
            raise TypeError("protected_path_violations entries must be str")


def build_dry_run_snapshot(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    generated_at_utc: str,
    preconditions: dict[str, bool],
    recommendation_action_seen: str,
    recommendation_reason_seen: str,
    merge_state_status_seen: str,
    required_checks_summary: dict[str, str],
    required_checks_granularity: str,
    protected_path_violations: list[str],
    protected_path_granularity: str,
    would_proceed: bool,
    stop_condition: str | None,
) -> dict[str, Any]:
    """Build the closed-schema dry-run snapshot dict. Pure — no I/O.

    ``preconditions`` must contain exactly :data:`DRY_RUN_PRECONDITION_KEYS`,
    each value a ``bool``.
    ``required_checks_granularity`` must be in
    :data:`REQUIRED_CHECKS_GRANULARITY_VALUES`.
    ``protected_path_granularity`` must be in
    :data:`PROTECTED_PATH_GRANULARITY_VALUES`.
    ``stop_condition`` must be ``None`` (when ``would_proceed=True``)
    or a member of :data:`B2_8D_STOP_CONDITIONS`. ``would_proceed=True``
    requires ``stop_condition=None``.
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
    _validate_preconditions_dict(preconditions)
    if not isinstance(recommendation_action_seen, str):
        raise TypeError("recommendation_action_seen must be str")
    if not isinstance(recommendation_reason_seen, str):
        raise TypeError("recommendation_reason_seen must be str")
    if not isinstance(merge_state_status_seen, str):
        raise TypeError("merge_state_status_seen must be str")
    _validate_required_checks_summary(required_checks_summary)
    if required_checks_granularity not in REQUIRED_CHECKS_GRANULARITY_VALUES:
        raise ValueError(
            "required_checks_granularity must be one of "
            f"{REQUIRED_CHECKS_GRANULARITY_VALUES}; "
            f"got {required_checks_granularity!r}"
        )
    _validate_protected_path_violations(protected_path_violations)
    if protected_path_granularity not in PROTECTED_PATH_GRANULARITY_VALUES:
        raise ValueError(
            "protected_path_granularity must be one of "
            f"{PROTECTED_PATH_GRANULARITY_VALUES}; "
            f"got {protected_path_granularity!r}"
        )
    if not isinstance(would_proceed, bool):
        raise TypeError("would_proceed must be bool")
    if would_proceed and stop_condition is not None:
        raise ValueError(
            "would_proceed=True requires stop_condition=None"
        )
    if not would_proceed and stop_condition is None:
        raise ValueError(
            "would_proceed=False requires a non-null stop_condition"
        )
    if stop_condition is not None and stop_condition not in B2_8D_STOP_CONDITIONS:
        raise ValueError(
            "stop_condition must be one of "
            f"{B2_8D_STOP_CONDITIONS}; got {stop_condition!r}"
        )

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": DRY_RUN_REPORT_KIND,
        "module_version": MODULE_VERSION,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "pr_base_ref": PR_BASE_REF,
        "intent": DRY_RUN_INTENT,
        "token_kid": token_kid,
        "nonce_hash": nonce_hash,
        "operator_actor": operator_actor,
        "generated_at_utc": generated_at_utc,
        "preconditions": dict(preconditions),
        "recommendation_action_seen": recommendation_action_seen,
        "recommendation_reason_seen": recommendation_reason_seen,
        "merge_state_status_seen": merge_state_status_seen,
        "required_checks_summary": dict(required_checks_summary),
        "required_checks_granularity": required_checks_granularity,
        "protected_path_violations": list(protected_path_violations),
        "protected_path_granularity": protected_path_granularity,
        "would_proceed": would_proceed,
        "stop_condition": stop_condition,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "level6_enabled": False,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    assert set(snapshot.keys()) == set(DRY_RUN_SNAPSHOT_KEYS), (
        f"dry_run snapshot key drift: {sorted(snapshot.keys())!r} vs "
        f"{sorted(DRY_RUN_SNAPSHOT_KEYS)!r}"
    )
    return snapshot


def write_dry_run_latest(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    generated_at_utc: str,
    preconditions: dict[str, bool],
    recommendation_action_seen: str,
    recommendation_reason_seen: str,
    merge_state_status_seen: str,
    required_checks_summary: dict[str, str],
    required_checks_granularity: str,
    protected_path_violations: list[str],
    protected_path_granularity: str,
    would_proceed: bool,
    stop_condition: str | None,
    target_path: Path | None = None,
) -> Path:
    """Build + persist the closed-schema dry-run snapshot to
    ``logs/n5b_merge_execution/dry_run/latest.json``.

    Sentinel-restricted via :func:`_atomic_write_json`;
    :func:`assert_no_secrets` runs on the payload first.
    ``target_path`` is exposed for unit-test isolation."""
    snapshot = build_dry_run_snapshot(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
        operator_actor=operator_actor,
        generated_at_utc=generated_at_utc,
        preconditions=preconditions,
        recommendation_action_seen=recommendation_action_seen,
        recommendation_reason_seen=recommendation_reason_seen,
        merge_state_status_seen=merge_state_status_seen,
        required_checks_summary=required_checks_summary,
        required_checks_granularity=required_checks_granularity,
        protected_path_violations=protected_path_violations,
        protected_path_granularity=protected_path_granularity,
        would_proceed=would_proceed,
        stop_condition=stop_condition,
    )
    target = target_path if target_path is not None else DRY_RUN_LATEST
    _atomic_write_json(target, snapshot)
    return target


def append_dry_run_history(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    generated_at_utc: str,
    preconditions: dict[str, bool],
    recommendation_action_seen: str,
    recommendation_reason_seen: str,
    merge_state_status_seen: str,
    required_checks_summary: dict[str, str],
    required_checks_granularity: str,
    protected_path_violations: list[str],
    protected_path_granularity: str,
    would_proceed: bool,
    stop_condition: str | None,
    target_path: Path | None = None,
) -> Path:
    """Append the closed-schema dry-run snapshot to
    ``logs/n5b_merge_execution/dry_run/history.jsonl`` (one JSON
    object per line). Atomic-replaces the file after compaction to
    the newest :data:`MAX_HISTORY_ROWS` rows.

    Sentinel-restricted: the path must contain :data:`WRITE_PREFIX`.
    :func:`assert_no_secrets` runs on the new snapshot before write.
    """
    snapshot = build_dry_run_snapshot(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
        operator_actor=operator_actor,
        generated_at_utc=generated_at_utc,
        preconditions=preconditions,
        recommendation_action_seen=recommendation_action_seen,
        recommendation_reason_seen=recommendation_reason_seen,
        merge_state_status_seen=merge_state_status_seen,
        required_checks_summary=required_checks_summary,
        required_checks_granularity=required_checks_granularity,
        protected_path_violations=protected_path_violations,
        protected_path_granularity=protected_path_granularity,
        would_proceed=would_proceed,
        stop_condition=stop_condition,
    )
    target = target_path if target_path is not None else DRY_RUN_HISTORY
    posix = target.as_posix()
    if WRITE_PREFIX not in posix:
        raise ValueError(
            "n5b_merge_execution_dry_run.append_dry_run_history refuses "
            f"non-N5b-logs output path: {target}"
        )
    assert_no_secrets(snapshot)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_lines: list[str] = []
    if target.is_file():
        try:
            existing_text = target.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""
        for line in existing_text.splitlines():
            stripped = line.strip()
            if stripped:
                existing_lines.append(stripped)
    new_line = json.dumps(snapshot, sort_keys=True)
    existing_lines.append(new_line)
    if len(existing_lines) > MAX_HISTORY_ROWS:
        existing_lines = existing_lines[-MAX_HISTORY_ROWS:]
    text = "\n".join(existing_lines) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".n5b_merge_execution_dry_run.history.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


__all__ = [
    "B2_8D_STOP_CONDITIONS",
    "DRY_RUN_DIR",
    "DRY_RUN_HISTORY",
    "DRY_RUN_HISTORY_RELATIVE",
    "DRY_RUN_INTENT",
    "DRY_RUN_LATEST",
    "DRY_RUN_LATEST_RELATIVE",
    "DRY_RUN_PRECONDITION_COUNT",
    "DRY_RUN_PRECONDITION_KEYS",
    "DRY_RUN_REPORT_KIND",
    "DRY_RUN_SNAPSHOT_KEYS",
    "FAILURE_DIR",
    "FAILURE_DIR_RELATIVE",
    "FAILURE_REPORT_KIND",
    "FAILURE_SNAPSHOT_KEYS",
    "MAX_HISTORY_ROWS",
    "MAX_STOP_REASON_LEN",
    "MODULE_VERSION",
    "OPERATOR_ACTORS",
    "PREFLIGHT_DIR",
    "PREFLIGHT_LATEST",
    "PREFLIGHT_LATEST_RELATIVE",
    "PREFLIGHT_SNAPSHOT_KEYS",
    "PROTECTED_PATH_GRANULARITY_VALUES",
    "PR_BASE_REF",
    "REPORT_KIND",
    "REQUIRED_CHECKS_GRANULARITY_VALUES",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "WRITE_PREFIX",
    "append_dry_run_history",
    "build_dry_run_snapshot",
    "build_failure_snapshot",
    "build_preflight_snapshot",
    "step5_implementation_allowed",
    "write_dry_run_latest",
    "write_failure",
    "write_preflight",
]
