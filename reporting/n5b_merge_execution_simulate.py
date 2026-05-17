"""N5b Phase 3 — Recorded-fixture simulator projector (B2.9b).

Stdlib-only pure projector for the future N5b Phase 3
**recorded-fixture simulator** endpoint described in
``docs/governance/n5b_phase3_implementation_plan.md``.

Phase 3 path selection: **recorded-fixture simulator**. The
sacrificial-GitHub-repository path is rejected (see §1.4 of the
sub-plan). This module never calls GitHub, never opens a
network socket, never spawns a subprocess, never reads an
environment variable.

This module ONLY:

* Reads a closed-schema on-disk JSON fixture (caller-supplied
  ``Path``; operator-provided on the VPS; gitignored; never
  committed) and validates it against the closed
  :data:`FIXTURE_SCHEMA_KEYS` shape.
* Builds a closed-schema simulation snapshot dict via
  :func:`build_simulate_snapshot` (pure — no I/O).
* Writes ``logs/n5b_merge_execution/phase3_simulation/latest.json``
  via :func:`write_simulate_latest`.
* Appends ``logs/n5b_merge_execution/phase3_simulation/history.jsonl``
  via :func:`append_simulate_history` (bounded by
  :data:`MAX_HISTORY_ROWS`, atomic-replace after compaction).

Hard guarantees (pinned by tests):

* Stdlib + :func:`reporting.agent_audit_summary.assert_no_secrets`
  (read-only redactor guard). No other imports.
* No subprocess, no socket, no urllib, no requests, no httpx, no
  aiohttp, no asyncio.
* No GitHub CLI literal, no version-control CLI literal, no
  branch-protection-bypass admin flag, no PR-mutation attribute
  name literal.
* No environment-variable read (the caller supplies the
  fixture path; the dashboard module alone is responsible for
  resolving env-configured paths).
* Atomic write via ``tempfile.mkstemp`` + ``os.replace``.
* Sentinel-restricted write prefix: any write whose absolute
  path does not contain ``logs/n5b_merge_execution/`` raises
  ``ValueError`` BEFORE the temp file is created.
* :func:`reporting.agent_audit_summary.assert_no_secrets` runs
  on the snapshot before write; a credential-shaped string
  aborts with ``AssertionError`` and no file is created.
* Closed snapshot schema (key-set check) — drift fails the pin
  test in the same PR that introduces the change.
* Closed fixture schema (key-set check) — drift fails the pin
  test. Unknown fixture keys are rejected.
* The closed ``simulator_safety_invariants`` dict is emitted
  into every artefact with every boolean nailed to True:
  ``no_real_github_merge``, ``no_production_merge``,
  ``no_network``, ``no_git_or_gh_or_subprocess``,
  ``no_step5_runtime``, ``no_level6``, ``no_live_trading``,
  ``no_paper_shadow_runtime``.
* :data:`step5_implementation_allowed` is ``Final[False]``;
  :data:`STEP5_ENABLED_SUBSTAGE` is ``Final["none"]``;
  ``level6_enabled`` is always ``False``.
* The projector never accepts the raw nonce or the raw token —
  only the caller-supplied ``token_kid`` (verified) and
  ``nonce_hash`` (sha256 hex of the verified nonce). The closed
  schema does not contain a ``token`` field or a raw ``nonce``
  field.
* The Phase 4 production-merge target-classification literal is
  NEVER emitted by this projector; the closed
  ``target_classification`` vocab is the singleton
  ``("recorded_fixture_simulator",)``.
* ``report_kind`` is the closed singleton ``"n5b_phase3_simulation"``
  — the Phase 4 execution-artefact ``report_kind`` (reserved
  for the Phase 4 production-merge endpoint, permanently denied
  for ADE per the sub-plan §5.1) is NOT emitted by this module.
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
MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase3.simulator_projector"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed write-prefix + repo-relative artefact paths
# ---------------------------------------------------------------------------

#: Sentinel substring that EVERY write path must contain. Same
#: prefix as B2.8c-e — no new sentinel introduced. Phase 3 adds
#: only the ``phase3_simulation/`` subdirectory under it.
WRITE_PREFIX: Final[str] = "logs/n5b_merge_execution/"

PHASE3_SIMULATION_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "n5b_merge_execution" / "phase3_simulation"
)
PHASE3_SIMULATION_LATEST: Final[Path] = PHASE3_SIMULATION_DIR / "latest.json"
PHASE3_SIMULATION_LATEST_RELATIVE: Final[str] = (
    "logs/n5b_merge_execution/phase3_simulation/latest.json"
)
PHASE3_SIMULATION_HISTORY: Final[Path] = (
    PHASE3_SIMULATION_DIR / "history.jsonl"
)
PHASE3_SIMULATION_HISTORY_RELATIVE: Final[str] = (
    "logs/n5b_merge_execution/phase3_simulation/history.jsonl"
)

#: Bounded history retention. Each append compacts to the newest
#: :data:`MAX_HISTORY_ROWS` rows so the file size stays bounded.
MAX_HISTORY_ROWS: Final[int] = 1024


# ---------------------------------------------------------------------------
# Closed allowed values
# ---------------------------------------------------------------------------

#: Pinned ``report_kind`` literal — singleton.
REPORT_KIND: Final[str] = "n5b_phase3_simulation"

#: Closed ``target_classification`` singleton vocab. The Phase 4
#: production-merge target-classification literal is NEVER
#: emitted by this projector — pinned by the negative source-
#: text scan in the companion test file.
TARGET_CLASSIFICATION_VALUES: Final[tuple[str, ...]] = (
    "recorded_fixture_simulator",
)

#: Closed ``mode`` singleton vocab.
MODE_VALUES: Final[tuple[str, ...]] = ("simulate_only",)

#: Closed merge-response classification vocab — mirrors parent
#: doc §6.4 (execution artefact) but is consumed via fixture
#: replay only.
MERGE_CLASSIFICATION_VALUES: Final[tuple[str, ...]] = (
    "merged_ok",
    "merged_with_warnings",
    "refused_by_github",
    "network_uncertain",
)

#: The ONLY base ref the simulator records (parent §3 row 12).
PR_BASE_REF: Final[str] = "main"

#: The pinned dry-run intent literal — reused from B2.8e. No
#: new N4b intent added.
DRY_RUN_INTENT: Final[str] = "mobile_approval_dispatch"

#: Closed operator-actor vocab — same as B2.8c-e.
OPERATOR_ACTORS: Final[tuple[str, ...]] = ("session", "operator_token")

#: Closed operator-confirmation-marker singleton — the Phase 3
#: second-confirmation literal.
OPERATOR_CONFIRMATION_MARKER: Final[str] = "simulator_execute_confirmed"


# ---------------------------------------------------------------------------
# Closed fixture schema
# ---------------------------------------------------------------------------

#: Pinned ``fixture_kind`` literal — singleton.
FIXTURE_KIND: Final[str] = "n5b_phase3_recorded_merge_simulation"

#: Top-level fixture key set. Drift fails the pin test.
FIXTURE_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "fixture_schema_version",
    "fixture_kind",
    "merge_response",
    "generated_at_utc",
    "fixture_notes",
)

#: Required fixture-keys (``fixture_notes`` is optional).
FIXTURE_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "fixture_schema_version",
    "fixture_kind",
    "merge_response",
    "generated_at_utc",
)

#: Required ``merge_response`` block key set.
FIXTURE_MERGE_RESPONSE_KEYS: Final[tuple[str, ...]] = (
    "http_status",
    "classification",
    "post_merge_head_sha",
    "merge_method",
    "delete_branch",
)

#: The only ``merge_method`` value the simulator accepts.
ACCEPTED_MERGE_METHOD: Final[str] = "squash"


# ---------------------------------------------------------------------------
# Safety invariants — emitted into every artefact, all True
# ---------------------------------------------------------------------------

_SIMULATOR_SAFETY_INVARIANTS: Final[dict[str, bool]] = {
    "no_real_github_merge": True,
    "no_production_merge": True,
    "no_network": True,
    "no_git_or_gh_or_subprocess": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_live_trading": True,
    "no_paper_shadow_runtime": True,
}

#: Closed safety-invariant key set. Drift fails the pin test.
SIMULATOR_SAFETY_INVARIANT_KEYS: Final[tuple[str, ...]] = tuple(
    sorted(_SIMULATOR_SAFETY_INVARIANTS.keys())
)


# ---------------------------------------------------------------------------
# Discipline invariants — mirrored into every artefact
# (matches the B2.8c-e shape verbatim)
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
# Closed simulation snapshot schema (exact key set)
# ---------------------------------------------------------------------------

SIMULATE_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
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
    "operator_confirmation_marker",
    "generated_at_utc",
    "target_classification",
    "mode",
    "fixture_kind",
    "fixture_schema_version",
    "fixture_generated_at_utc",
    "merge_response_http_status",
    "merge_response_classification",
    "merge_response_post_merge_head_sha",
    "merge_response_merge_method",
    "merge_response_delete_branch",
    "would_proceed",
    "simulator_safety_invariants",
    "step5_implementation_allowed",
    "step5_enabled_substage",
    "level6_enabled",
    "dry_run_only",
    "live_merge_implemented",
    "deploy_coupled",
    "discipline_invariants",
)


# ---------------------------------------------------------------------------
# Fixture reader (no env, no network, no subprocess)
# ---------------------------------------------------------------------------


def read_fixture(path: Path) -> dict[str, Any]:
    """Read + validate a recorded-fixture JSON file from disk.

    The caller supplies the path; this module never resolves a
    fixture path from an environment variable. The fixture is
    operator-provided, gitignored, never committed.

    Raises:
      :class:`FileNotFoundError` if ``path`` does not exist.
      :class:`ValueError` for any closed-schema validation failure.
    """
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    if not path.is_file():
        raise FileNotFoundError(f"fixture file missing: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"fixture unreadable: {type(exc).__name__}") from exc
    try:
        data = json.loads(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"fixture unparseable as JSON: {type(exc).__name__}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("fixture top-level must be a JSON object")
    # Closed-shape check. Unknown keys rejected.
    extra = set(data.keys()) - set(FIXTURE_SCHEMA_KEYS)
    if extra:
        raise ValueError(
            f"fixture contains unknown top-level keys: {sorted(extra)!r}"
        )
    missing = set(FIXTURE_REQUIRED_KEYS) - set(data.keys())
    if missing:
        raise ValueError(
            f"fixture missing required keys: {sorted(missing)!r}"
        )
    if data.get("fixture_kind") != FIXTURE_KIND:
        raise ValueError(
            f"fixture_kind must be {FIXTURE_KIND!r}; "
            f"got {data.get('fixture_kind')!r}"
        )
    try:
        sv = int(data.get("fixture_schema_version") or 0)
    except (TypeError, ValueError):
        raise ValueError("fixture_schema_version must be int")
    if sv != SCHEMA_VERSION:
        raise ValueError(
            f"fixture_schema_version must be {SCHEMA_VERSION}; got {sv}"
        )
    generated_at = data.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError("fixture.generated_at_utc must be a non-empty string")
    notes = data.get("fixture_notes", "")
    if not isinstance(notes, str):
        raise ValueError("fixture.fixture_notes must be a string when present")
    if len(notes) > 500:
        raise ValueError("fixture.fixture_notes exceeds 500 chars")

    mr = data.get("merge_response")
    if not isinstance(mr, dict):
        raise ValueError("fixture.merge_response must be a JSON object")
    extra_mr = set(mr.keys()) - set(FIXTURE_MERGE_RESPONSE_KEYS)
    if extra_mr:
        raise ValueError(
            f"fixture.merge_response contains unknown keys: "
            f"{sorted(extra_mr)!r}"
        )
    missing_mr = set(FIXTURE_MERGE_RESPONSE_KEYS) - set(mr.keys())
    if missing_mr:
        raise ValueError(
            f"fixture.merge_response missing required keys: "
            f"{sorted(missing_mr)!r}"
        )
    http_status = mr.get("http_status")
    if not isinstance(http_status, int) or isinstance(http_status, bool):
        raise ValueError("merge_response.http_status must be int")
    if http_status < 100 or http_status > 599:
        raise ValueError("merge_response.http_status out of HTTP range")
    classification = mr.get("classification")
    if classification not in MERGE_CLASSIFICATION_VALUES:
        raise ValueError(
            f"merge_response.classification must be in "
            f"{MERGE_CLASSIFICATION_VALUES}; got {classification!r}"
        )
    sha = mr.get("post_merge_head_sha")
    if not isinstance(sha, str) or not sha:
        raise ValueError("merge_response.post_merge_head_sha must be non-empty str")
    if len(sha) > 64:
        raise ValueError("merge_response.post_merge_head_sha exceeds 64 chars")
    method = mr.get("merge_method")
    if method != ACCEPTED_MERGE_METHOD:
        raise ValueError(
            f"merge_response.merge_method must be {ACCEPTED_MERGE_METHOD!r}; "
            f"got {method!r}"
        )
    delete_branch = mr.get("delete_branch")
    if not isinstance(delete_branch, bool):
        raise ValueError("merge_response.delete_branch must be bool")
    return data


# ---------------------------------------------------------------------------
# Snapshot builder (pure, deterministic — no I/O)
# ---------------------------------------------------------------------------


def build_simulate_snapshot(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    operator_confirmation_marker: str,
    generated_at_utc: str,
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Build the closed-schema simulation snapshot dict.

    Pure — no I/O. Caller supplies the validated fixture dict
    (typically the return value of :func:`read_fixture`).

    Raises:
      :class:`TypeError` if ``pr_number`` is not ``int`` (or is
      ``bool``).
      :class:`ValueError` for any value-shape or vocabulary
      failure.
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
            f"operator_actor must be one of {OPERATOR_ACTORS}; "
            f"got {operator_actor!r}"
        )
    if operator_confirmation_marker != OPERATOR_CONFIRMATION_MARKER:
        raise ValueError(
            f"operator_confirmation_marker must be "
            f"{OPERATOR_CONFIRMATION_MARKER!r}; "
            f"got {operator_confirmation_marker!r}"
        )
    if not isinstance(generated_at_utc, str) or not generated_at_utc:
        raise ValueError("generated_at_utc must be a non-empty ISO 8601 string")
    # Defensive: validate the fixture once more even though
    # ``read_fixture`` already did. Cheap and pin-stable.
    if not isinstance(fixture, dict):
        raise TypeError("fixture must be a dict")
    if fixture.get("fixture_kind") != FIXTURE_KIND:
        raise ValueError("fixture.fixture_kind must be the closed singleton")
    mr = fixture.get("merge_response")
    if not isinstance(mr, dict):
        raise ValueError("fixture.merge_response must be a dict")

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
        "operator_confirmation_marker": operator_confirmation_marker,
        "generated_at_utc": generated_at_utc,
        "target_classification": "recorded_fixture_simulator",
        "mode": "simulate_only",
        "fixture_kind": FIXTURE_KIND,
        "fixture_schema_version": SCHEMA_VERSION,
        "fixture_generated_at_utc": str(fixture.get("generated_at_utc") or ""),
        "merge_response_http_status": int(mr.get("http_status") or 0),
        "merge_response_classification": str(mr.get("classification") or ""),
        "merge_response_post_merge_head_sha": str(
            mr.get("post_merge_head_sha") or ""
        ),
        "merge_response_merge_method": str(mr.get("merge_method") or ""),
        "merge_response_delete_branch": bool(mr.get("delete_branch")),
        "would_proceed": True,
        "simulator_safety_invariants": dict(_SIMULATOR_SAFETY_INVARIANTS),
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "level6_enabled": False,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    # Closed-shape check.
    assert set(snapshot.keys()) == set(SIMULATE_SNAPSHOT_KEYS), (
        f"simulate snapshot key drift: {sorted(snapshot.keys())!r} vs "
        f"{sorted(SIMULATE_SNAPSHOT_KEYS)!r}"
    )
    # Pin the target_classification + mode against the closed vocabs.
    assert (
        snapshot["target_classification"] in TARGET_CLASSIFICATION_VALUES
    ), (
        f"target_classification {snapshot['target_classification']!r} "
        f"not in closed vocab {TARGET_CLASSIFICATION_VALUES!r}"
    )
    assert snapshot["mode"] in MODE_VALUES, (
        f"mode {snapshot['mode']!r} not in closed vocab {MODE_VALUES!r}"
    )
    return snapshot


# ---------------------------------------------------------------------------
# Sentinel-restricted atomic writer + history append
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` atomically.

    Sentinel-restricted: ``path`` MUST contain
    :data:`WRITE_PREFIX` in its POSIX-form string. Otherwise
    raises ``ValueError`` BEFORE the temp file is created.

    ``assert_no_secrets`` is invoked on ``payload`` first. A
    credential-shaped string aborts the write with
    ``AssertionError``.
    """
    posix = path.as_posix()
    if WRITE_PREFIX not in posix:
        raise ValueError(
            "n5b_merge_execution_simulate._atomic_write_json refuses "
            f"non-N5b-logs output path: {path}"
        )
    assert_no_secrets(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".n5b_merge_execution_simulate.",
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


def write_simulate_latest(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    operator_confirmation_marker: str,
    generated_at_utc: str,
    fixture: dict[str, Any],
    target_path: Path | None = None,
) -> Path:
    """Build + persist the closed-schema simulation snapshot to
    ``logs/n5b_merge_execution/phase3_simulation/latest.json``.

    Sentinel-restricted via :func:`_atomic_write_json`;
    :func:`assert_no_secrets` runs on the payload first.
    ``target_path`` is exposed for unit-test isolation."""
    snapshot = build_simulate_snapshot(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
        operator_actor=operator_actor,
        operator_confirmation_marker=operator_confirmation_marker,
        generated_at_utc=generated_at_utc,
        fixture=fixture,
    )
    target = target_path if target_path is not None else PHASE3_SIMULATION_LATEST
    _atomic_write_json(target, snapshot)
    return target


def append_simulate_history(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    operator_actor: str,
    operator_confirmation_marker: str,
    generated_at_utc: str,
    fixture: dict[str, Any],
    target_path: Path | None = None,
) -> Path:
    """Append the closed-schema simulation snapshot to
    ``logs/n5b_merge_execution/phase3_simulation/history.jsonl``
    (one JSON object per line). Atomic-replaces the file after
    compaction to the newest :data:`MAX_HISTORY_ROWS` rows.

    Sentinel-restricted: the path must contain :data:`WRITE_PREFIX`.
    :func:`assert_no_secrets` runs on the new snapshot before write.
    """
    snapshot = build_simulate_snapshot(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
        operator_actor=operator_actor,
        operator_confirmation_marker=operator_confirmation_marker,
        generated_at_utc=generated_at_utc,
        fixture=fixture,
    )
    target = (
        target_path if target_path is not None else PHASE3_SIMULATION_HISTORY
    )
    posix = target.as_posix()
    if WRITE_PREFIX not in posix:
        raise ValueError(
            "n5b_merge_execution_simulate.append_simulate_history refuses "
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
        prefix=".n5b_merge_execution_simulate.history.",
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
    "ACCEPTED_MERGE_METHOD",
    "DRY_RUN_INTENT",
    "FIXTURE_KIND",
    "FIXTURE_MERGE_RESPONSE_KEYS",
    "FIXTURE_REQUIRED_KEYS",
    "FIXTURE_SCHEMA_KEYS",
    "MAX_HISTORY_ROWS",
    "MERGE_CLASSIFICATION_VALUES",
    "MODE_VALUES",
    "MODULE_VERSION",
    "OPERATOR_ACTORS",
    "OPERATOR_CONFIRMATION_MARKER",
    "PHASE3_SIMULATION_DIR",
    "PHASE3_SIMULATION_HISTORY",
    "PHASE3_SIMULATION_HISTORY_RELATIVE",
    "PHASE3_SIMULATION_LATEST",
    "PHASE3_SIMULATION_LATEST_RELATIVE",
    "PR_BASE_REF",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "SIMULATE_SNAPSHOT_KEYS",
    "SIMULATOR_SAFETY_INVARIANT_KEYS",
    "STEP5_ENABLED_SUBSTAGE",
    "TARGET_CLASSIFICATION_VALUES",
    "WRITE_PREFIX",
    "append_simulate_history",
    "build_simulate_snapshot",
    "read_fixture",
    "step5_implementation_allowed",
    "write_simulate_latest",
]
