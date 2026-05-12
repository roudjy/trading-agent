"""N5b Phase 1 — dry-run merge preflight projector (read-only).

Pure stdlib projector that joins the existing read-only artefacts

* **A23 / N5a** merge recommendation rows at
  ``logs/development_merge_recommendation/latest.json``;
* **A22** PR-lifecycle observer rows at
  ``logs/development_pr_lifecycle_observer/latest.json``;

into a closed-schema **dry-run preflight** artefact at
``logs/development_merge_preflight/latest.json``. For each
recommendation row, the projector evaluates the dry-run
preconditions that a hypothetical future N5b live-merge adapter
would have to satisfy, and emits a closed-vocab verdict — without
ever calling GitHub, ``gh``, ``git``, a subprocess, a network
socket, or the N4b approval-token runtime.

This is the **first** safe N5b-execution-adjacent slice and is
deliberately **read-only**:

* No merge.
* No GitHub mutation.
* No PR comment.
* No deploy.
* No token mint, no token verify.
* No write outside ``logs/development_merge_preflight/...``.

The artefact reports per-PR fields like ``dry_run_verdict``,
``stop_conditions``, ``token_required_for_live`` (always True),
and ``live_merge_implemented`` (always False). Operator reads the
artefact (CLI or future read-only dashboard) to understand what
would block a hypothetical live merge — but no live merge endpoint
exists. Phase 2+ and any live merge execution require separate,
explicit operator-go per
``docs/governance/n5b_merge_execution_plan.md`` §10.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.development_merge_recommendation`` (closed
  vocab + artefact path constants) + ``reporting.development_pr_lifecycle_observer``
  (closed vocab + artefact path constants) + ``reporting.agent_audit_summary.assert_no_secrets``.
* No subprocess, no network, no GitHub CLI, no ``git`` invocation,
  no GitHub API HTTP call.
* No import of dashboard / frontend / automation / broker /
  agent.risk / agent.execution / research / intelligent-routing /
  live / paper / shadow / trading / approval-token runtime
  modules — the per-test forbidden-import list pins every
  prefix explicitly.
* No process-environment read of any kind. The companion
  pin-test forbids the canonical env-read attribute names from
  appearing in the source.
* No write to any seed-style JSONL file. The companion pin-test
  forbids the canonical seed filenames from appearing in the
  source.
* Atomic write only under ``logs/development_merge_preflight/...``
  via tmp + ``os.replace``, sentinel-restricted to the closed
  write prefix.
* Per-row schema is closed and exact; bounded scalars only.
* The verdict closed vocab uses ``would_*`` prefixes that are
  explicitly NOT decision verbs themselves
  (``would_block`` / ``would_require_operator`` /
  ``would_be_live_candidate_if_authorized``).
* ``step5_implementation_allowed`` remains ``False``,
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``,
  ``level6_enabled`` is always ``False``.
* Default-deny: when artefacts are missing, malformed, or any
  precondition is uncertain, the verdict is ``would_block`` (or
  the candidate is omitted with a top-level warning).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_merge_recommendation as dmr
from reporting import development_pr_lifecycle_observer as a22
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase1"
REPORT_KIND: Final[str] = "development_merge_preflight"

# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed verdict vocabulary
#
# Every value uses a ``would_*`` prefix to make explicit that this
# is a DRY-RUN report. None of the values is itself a decision verb
# (no ``approve``, no ``merge``, no ``deploy``).
# ---------------------------------------------------------------------------

DRY_RUN_VERDICTS: Final[tuple[str, ...]] = (
    "would_block",
    "would_require_operator",
    "would_be_live_candidate_if_authorized",
)


# ---------------------------------------------------------------------------
# Closed stop-condition vocabulary
# ---------------------------------------------------------------------------

STOP_CONDITIONS: Final[tuple[str, ...]] = (
    "missing_merge_recommendation_artifact",
    "malformed_merge_recommendation_artifact",
    "missing_pr_lifecycle_artifact",
    "malformed_pr_lifecycle_artifact",
    "recommendation_not_merge",
    "missing_pr_number",
    "missing_head_sha",
    "base_ref_not_main",
    "merge_state_not_clean",
    "checks_not_green",
    "head_sha_mismatch",
    "critical_inbox_rows_present",
    "stale_recommendation",
    "token_required_for_live",
    "live_merge_not_implemented",
    "insufficient_evidence",
)

#: Stop conditions that are *informational* — they remind the
#: operator that this is a dry-run and that no live merge is
#: implemented. They are emitted on every candidate but do NOT
#: by themselves downgrade the verdict to ``would_block``.
_INFORMATIONAL_STOP_CONDITIONS: Final[frozenset[str]] = frozenset(
    {"token_required_for_live", "live_merge_not_implemented"}
)


# ---------------------------------------------------------------------------
# Closed validation-warning vocabulary
# ---------------------------------------------------------------------------

VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "merge_recommendation_artifact_absent",
    "merge_recommendation_artifact_unparseable",
    "pr_lifecycle_artifact_absent",
    "pr_lifecycle_artifact_unparseable",
    "no_recommendation_rows",
)


# ---------------------------------------------------------------------------
# Wrapper-level note vocabulary
# ---------------------------------------------------------------------------

NOTE_NO_RECOMMENDATION: Final[str] = "missing_merge_recommendation_artifact"
NOTE_NO_LIFECYCLE: Final[str] = "missing_pr_lifecycle_artifact"
NOTE_NO_CANDIDATES: Final[str] = "no_recommendation_rows"
NOTE_CANDIDATES_PRESENT: Final[str] = "candidates_present"


# ---------------------------------------------------------------------------
# Per-row closed schema (18 keys, exact and ordered)
# ---------------------------------------------------------------------------

CANDIDATE_ROW_KEYS: Final[tuple[str, ...]] = (
    "preflight_id",
    "recommendation_id",
    "pr_number",
    "expected_head_sha",
    "observed_head_sha",
    "base_ref",
    "head_ref",
    "merge_state",
    "checks_state",
    "recommendation_action",
    "recommendation_reason",
    "token_required_for_live",
    "dry_run_verdict",
    "live_merge_implemented",
    "stop_conditions",
    "audit_note",
    "generated_at_utc",
    "evidence_freshness_seconds",
)


# ---------------------------------------------------------------------------
# Closed acceptance vocabularies for upstream-derived fields
# ---------------------------------------------------------------------------

#: Accepted GitHub ``mergeStateStatus`` values that mean "merge is
#: safe to attempt right now". Anything else triggers
#: ``merge_state_not_clean``.
_CLEAN_MERGE_STATES: Final[frozenset[str]] = frozenset({"CLEAN"})

#: Accepted GitHub status-check rollup values that mean "all
#: required checks are green". Anything else triggers
#: ``checks_not_green``.
_GREEN_CHECK_STATES: Final[frozenset[str]] = frozenset(
    {"SUCCESS", "PASSING", "PASSED"}
)

#: Closed N5a recommendation_action that means "human merge is the
#: appropriate next step". Any other action triggers
#: ``recommendation_not_merge``.
_HUMAN_MERGE_ACTION: Final[str] = "recommend_human_merge"


# ---------------------------------------------------------------------------
# Bounded scalar lengths + freshness window
# ---------------------------------------------------------------------------

#: Maximum candidate rows in any single snapshot. The N5a projector
#: already caps at 64; mirror that here.
MAX_CANDIDATE_ROWS: Final[int] = 64

#: Bounded length for the per-row ``audit_note`` scalar.
MAX_AUDIT_NOTE_LEN: Final[int] = 200

#: Recommendation freshness window. A recommendation older than
#: this is flagged with ``stale_recommendation`` per the N5b plan
#: doc §3 row 13. Exact threshold is bounded but liberal; the
#: operator can re-refresh the upstream N5a projector to refresh.
STALE_THRESHOLD_SECONDS: Final[int] = 60 * 60  # 60 minutes


# ---------------------------------------------------------------------------
# Repo-relative artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_merge_preflight"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_merge_preflight/latest.json"
)

#: Atomic-write allowlist (substring form). Any attempt to write
#: outside this prefix raises ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/development_merge_preflight/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
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
# Utility helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso_utc(value: Any) -> _dt.datetime | None:
    """Best-effort ISO-8601 parser. Returns ``None`` on any failure."""
    if not isinstance(value, str) or not value:
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _read_json(path: Path) -> tuple[str, dict[str, Any] | None]:
    """Return ``("ok", data)`` on success, ``("absent", None)`` if
    the file is missing, or ``("malformed", None)`` if the file
    exists but does not parse. Never raises."""
    if not path.is_file():
        return "absent", None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "malformed", None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return "malformed", None
    if not isinstance(data, dict):
        return "malformed", None
    return "ok", data


def _bounded(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len]


def _preflight_id(pr_number: int, expected_head_sha: str) -> str:
    """Stable preflight id derived from PR number + expected head
    SHA. Changes when either binding changes — which is exactly when
    the preflight verdict must be re-evaluated."""
    sha_prefix = expected_head_sha[:12] if isinstance(expected_head_sha, str) else ""
    return f"pf_{pr_number}_{sha_prefix}"


# ---------------------------------------------------------------------------
# Per-candidate evaluation (pure, deterministic)
# ---------------------------------------------------------------------------


def _safe_recommendation_rows(
    payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Defense-in-depth filter on the N5a row list. Returns only
    rows whose key-set matches the closed N5a schema."""
    if not isinstance(payload, dict):
        return []
    raw = payload.get("rows")
    if not isinstance(raw, list):
        return []
    expected = set(dmr.RECOMMENDATION_ROW_KEYS)
    out: list[dict[str, Any]] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        if set(r.keys()) != expected:
            continue
        out.append(r)
    return out[:MAX_CANDIDATE_ROWS]


def _index_lifecycle_rows(
    payload: dict[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    """Build a ``{pr_number: row}`` index from the A22 artefact."""
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("rows")
    if not isinstance(raw, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for r in raw:
        if not isinstance(r, dict):
            continue
        try:
            n = int(r.get("pr_number") or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            continue
        out[n] = r
    return out


def _evidence_freshness_seconds(
    n5a_evaluated_at: Any,
    now: _dt.datetime,
) -> int:
    """Return the freshness of the N5a recommendation row in
    seconds, or -1 if the timestamp is missing/unparseable. -1 is
    sentinel for ``unknown`` and triggers ``insufficient_evidence``
    upstream."""
    parsed = _parse_iso_utc(n5a_evaluated_at)
    if parsed is None:
        return -1
    delta = now - parsed
    return max(0, int(delta.total_seconds()))


def _evaluate_candidate(
    n5a_row: dict[str, Any],
    lifecycle_index: dict[int, dict[str, Any]],
    *,
    lifecycle_artifact_available: bool,
    now: _dt.datetime,
    evaluated_at: str,
) -> dict[str, Any]:
    """Map one N5a recommendation row + the matching A22 row into a
    closed-schema candidate row."""

    pr_number_raw = n5a_row.get("pr_number")
    try:
        pr_number = int(pr_number_raw or 0)
    except (TypeError, ValueError):
        pr_number = 0
    expected_head_sha = _bounded(n5a_row.get("head_sha"), 64)
    head_ref = _bounded(n5a_row.get("head_ref"), 200)
    base_ref = _bounded(n5a_row.get("base_ref") or "main", 200)
    recommendation_id = _bounded(n5a_row.get("recommendation_id"), 128)
    recommendation_action = str(n5a_row.get("recommendation_action") or "")
    recommendation_reason = str(n5a_row.get("recommendation_reason") or "")
    try:
        inbox_critical_count = int(n5a_row.get("inbox_critical_count") or 0)
    except (TypeError, ValueError):
        inbox_critical_count = 0

    a22_row = lifecycle_index.get(pr_number) if pr_number > 0 else None
    observed_head_sha = ""
    merge_state = ""
    checks_state = ""
    a22_base_ref = base_ref
    if isinstance(a22_row, dict):
        observed_head_sha = _bounded(a22_row.get("head_sha"), 64)
        merge_state = str(a22_row.get("merge_state_status") or "").upper()
        checks_state = str(a22_row.get("checks_summary") or "").upper()
        a22_base_ref_raw = _bounded(a22_row.get("base_ref"), 200)
        if a22_base_ref_raw:
            a22_base_ref = a22_base_ref_raw

    evidence_freshness = _evidence_freshness_seconds(
        n5a_row.get("evaluated_at"), now
    )

    # ---- Build per-row stop_conditions in deterministic order ----
    stop_conditions: list[str] = []

    if pr_number <= 0:
        stop_conditions.append("missing_pr_number")
    if not expected_head_sha:
        stop_conditions.append("missing_head_sha")
    if recommendation_action != _HUMAN_MERGE_ACTION:
        stop_conditions.append("recommendation_not_merge")
    if (a22_base_ref or "main").lower() != "main":
        stop_conditions.append("base_ref_not_main")

    if not lifecycle_artifact_available:
        # The lifecycle artefact is absent at the snapshot level.
        # We still emit a candidate row so the operator can see
        # which recommendations are awaiting a lifecycle refresh,
        # but every PR-side check is implicitly unknown.
        if "missing_head_sha" not in stop_conditions:
            stop_conditions.append("insufficient_evidence")
    elif a22_row is None:
        # Lifecycle artefact is present but no row for this PR.
        stop_conditions.append("insufficient_evidence")
    else:
        if merge_state not in _CLEAN_MERGE_STATES:
            stop_conditions.append("merge_state_not_clean")
        if checks_state not in _GREEN_CHECK_STATES:
            stop_conditions.append("checks_not_green")
        if (
            expected_head_sha
            and observed_head_sha
            and expected_head_sha != observed_head_sha
        ):
            stop_conditions.append("head_sha_mismatch")

    if inbox_critical_count > 0:
        stop_conditions.append("critical_inbox_rows_present")

    if (
        evidence_freshness >= 0
        and evidence_freshness > STALE_THRESHOLD_SECONDS
    ):
        stop_conditions.append("stale_recommendation")

    # Informational reminders. ALWAYS emitted; never by themselves
    # cause a downgrade past ``would_be_live_candidate_if_authorized``.
    stop_conditions.append("token_required_for_live")
    stop_conditions.append("live_merge_not_implemented")

    # ---- Derive verdict ----
    blocking = [
        sc for sc in stop_conditions if sc not in _INFORMATIONAL_STOP_CONDITIONS
    ]
    if not blocking:
        verdict = "would_be_live_candidate_if_authorized"
    elif "insufficient_evidence" in blocking and len(blocking) == 1:
        verdict = "would_require_operator"
    else:
        verdict = "would_block"

    audit_note = _bounded(
        (
            "dry-run only; no live merge route exists; "
            "verdict reflects the moment of evaluation"
        ),
        MAX_AUDIT_NOTE_LEN,
    )

    row: dict[str, Any] = {
        "preflight_id": _preflight_id(pr_number, expected_head_sha),
        "recommendation_id": recommendation_id,
        "pr_number": pr_number,
        "expected_head_sha": expected_head_sha,
        "observed_head_sha": observed_head_sha,
        "base_ref": a22_base_ref or base_ref,
        "head_ref": head_ref,
        "merge_state": merge_state,
        "checks_state": checks_state,
        "recommendation_action": recommendation_action,
        "recommendation_reason": recommendation_reason,
        "token_required_for_live": True,
        "dry_run_verdict": verdict,
        "live_merge_implemented": False,
        "stop_conditions": stop_conditions,
        "audit_note": audit_note,
        "generated_at_utc": evaluated_at,
        "evidence_freshness_seconds": evidence_freshness,
    }
    assert set(row.keys()) == set(CANDIDATE_ROW_KEYS), (
        f"candidate row key drift: {sorted(row.keys())!r} vs "
        f"{sorted(CANDIDATE_ROW_KEYS)!r}"
    )
    assert verdict in DRY_RUN_VERDICTS, (
        f"verdict {verdict!r} not in closed vocab {DRY_RUN_VERDICTS!r}"
    )
    for sc in stop_conditions:
        assert sc in STOP_CONDITIONS, (
            f"stop_condition {sc!r} not in closed vocab {STOP_CONDITIONS!r}"
        )
    return row


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "total": len(rows),
        "by_dry_run_verdict": {v: 0 for v in DRY_RUN_VERDICTS},
        "by_stop_condition": {sc: 0 for sc in STOP_CONDITIONS},
    }
    for row in rows:
        v = row.get("dry_run_verdict")
        if v in counts["by_dry_run_verdict"]:
            counts["by_dry_run_verdict"][v] += 1
        for sc in row.get("stop_conditions") or []:
            if sc in counts["by_stop_condition"]:
                counts["by_stop_condition"][sc] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    recommendation_artifact_path: Path | None = None,
    pr_observer_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic dry-run preflight snapshot. Pure —
    reads two read-only artefacts, performs no write of any kind."""
    rec_path = (
        recommendation_artifact_path
        if recommendation_artifact_path is not None
        else dmr.ARTIFACT_LATEST
    )
    lifecycle_path = (
        pr_observer_artifact_path
        if pr_observer_artifact_path is not None
        else a22.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    now_dt = _parse_iso_utc(ts) or _dt.datetime.now(_dt.UTC)

    rec_status, rec_payload = _read_json(rec_path)
    lifecycle_status, lifecycle_payload = _read_json(lifecycle_path)

    warnings: list[str] = []
    if rec_status == "absent":
        warnings.append("merge_recommendation_artifact_absent")
    elif rec_status == "malformed":
        warnings.append("merge_recommendation_artifact_unparseable")

    if lifecycle_status == "absent":
        warnings.append("pr_lifecycle_artifact_absent")
    elif lifecycle_status == "malformed":
        warnings.append("pr_lifecycle_artifact_unparseable")

    n5a_rows = _safe_recommendation_rows(rec_payload)
    lifecycle_index = _index_lifecycle_rows(lifecycle_payload)
    lifecycle_artifact_available = lifecycle_status == "ok"

    candidates: list[dict[str, Any]] = []
    for n5a_row in n5a_rows:
        if len(candidates) >= MAX_CANDIDATE_ROWS:
            break
        candidates.append(
            _evaluate_candidate(
                n5a_row,
                lifecycle_index,
                lifecycle_artifact_available=lifecycle_artifact_available,
                now=now_dt,
                evaluated_at=ts,
            )
        )

    candidates.sort(key=lambda r: (r["pr_number"], r["expected_head_sha"]))

    if not candidates:
        warnings.append("no_recommendation_rows")
        if rec_status != "ok":
            note = NOTE_NO_RECOMMENDATION
        elif lifecycle_status != "ok":
            note = NOTE_NO_LIFECYCLE
        else:
            note = NOTE_NO_CANDIDATES
    else:
        note = NOTE_CANDIDATES_PRESENT

    sources_read: dict[str, Any] = {
        "merge_recommendation_artifact": {
            "path": str(rec_path),
            "status": rec_status,
        },
        "pr_lifecycle_artifact": {
            "path": str(lifecycle_path),
            "status": lifecycle_status,
        },
    }

    counts = _aggregate_counts(candidates)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "generated_at_utc": ts,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "level6_enabled": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "sources_read": sources_read,
        "validation_warnings": warnings,
        "note": note,
        "stale_threshold_seconds": STALE_THRESHOLD_SECONDS,
        "max_candidate_rows": MAX_CANDIDATE_ROWS,
        "vocabularies": {
            "dry_run_verdicts": list(DRY_RUN_VERDICTS),
            "stop_conditions": list(STOP_CONDITIONS),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "candidate_row_keys": list(CANDIDATE_ROW_KEYS),
        },
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "upstream_module_versions": {
            "development_merge_recommendation": dmr.MODULE_VERSION,
            "development_pr_lifecycle_observer": a22.MODULE_VERSION,
        },
    }
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write (sentinel-restricted)
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_merge_preflight._atomic_write_json refuses "
            f"non-preflight-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_merge_preflight.",
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


def write_outputs(snapshot: dict[str, Any]) -> Path:
    """Persist the snapshot to ``logs/development_merge_preflight/latest.json``.
    Sentinel-restricted via :func:`_atomic_write_json`."""
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_merge_preflight",
        description=(
            "N5b Phase 1 dry-run merge preflight projector. Reads "
            "the existing N5a recommendation + A22 PR-lifecycle "
            "artefacts and emits a closed-schema dry-run preflight "
            "report. NEVER merges, NEVER calls GitHub / gh / git, "
            "NEVER mints or verifies an approval token."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_merge_preflight/latest.json (stdout only)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_snapshot()
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
