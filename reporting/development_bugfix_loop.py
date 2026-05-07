"""A10 — Agentic Bugfix Loop.

Pure, deterministic, stdlib-only **intake** module. Converts a
structured failure-summary contract into bounded bugfix-candidate
proposals. The module is intake/proposal **only**:

* it never writes to ``docs/development_work_queue/seed.jsonl``;
* it never writes to ``docs/development_work_queue/bugfix_seed.jsonl``;
* it emits proposals only to ``logs/development_bugfix_loop/latest.json``;
* operator promotion of any candidate into a queue seed file is a
  separate manual action.

The pure module never runs tests, never invokes ``pytest``, never
calls ``gh``/``git``/``subprocess``, and never imports test runners.
Failure summaries are produced **outside ADE core** by collectors
under ``scripts/`` (or by hand). ADE core only consumes the
contract; ADE core never imports collectors.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` + ``reporting.approval_policy`` +
  ``reporting.development_work_queue`` (read-only API).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* No mutation of any upstream artifact.
* Atomic write only under ``logs/development_bugfix_loop/latest.json``.
* Acceptance-criteria templates are drawn from a closed safe set;
  test-weakening suggestions (``skip``, ``xfail``, pin removal,
  assertion relaxation) are intentionally absent and pinned by
  tests.

CLI::

    python -m reporting.development_bugfix_loop
    python -m reporting.development_bugfix_loop --indent 2
    python -m reporting.development_bugfix_loop --no-write
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_work_queue as dwq
from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A10"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: 10 failure classes. Closed; additive only.
FAILURE_CLASSES: Final[tuple[str, ...]] = (
    "unit_test",
    "smoke_test",
    "regression_test",
    "lint",
    "typecheck",
    "governance_lint",
    "frozen_hash",
    "hook",
    "ci_workflow",
    "unknown",
)

#: 7 bugfix scopes. ``out_of_scope`` is the explicit "do not touch"
#: bucket — used for any failure whose only mechanical fix would
#: require test weakening or any other governance-violating action.
BUGFIX_SCOPES: Final[tuple[str, ...]] = (
    "bounded_in_repo",
    "protected_path",
    "live_path",
    "frozen_contract",
    "ci_only",
    "requires_architecture_review",
    "out_of_scope",
)

#: Closed severity vocabulary on the failure-input side.
INPUT_SEVERITIES: Final[tuple[str, ...]] = ("low", "medium", "high", "unknown")

#: Suggested status for the proposed candidate. Mirrors a subset of
#: the A8 Kanban statuses appropriate for an unpromoted proposal.
SUGGESTED_STATUSES: Final[tuple[str, ...]] = ("proposed", "human_needed")

#: Per-candidate schema keys, exact and ordered.
CANDIDATE_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "candidate_id",
    "failure_class",
    "target_path",
    "target_path_category",
    "bugfix_scope",
    "suggested_status",
    "suggested_required_agent_role",
    "suggested_category",
    "human_needed",
    "human_needed_reason",
    "execution_authority_decision",
    "execution_authority_reason",
    "repeat_count",
    "first_seen_utc",
    "last_seen_utc",
    "severity",
    "acceptance_criteria_template",
    "notes",
    "created_at_placeholder",
    "updated_at_placeholder",
)

ITEM_TIME_PLACEHOLDER: Final[str] = "deterministic_seed_placeholder"

#: Threshold for promoting a repeated failure to ``human_needed``.
REPEATED_FAILURE_THRESHOLD: Final[int] = 3

DEFAULT_INPUT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "bugfix_loop_input" / "latest.json"
)
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_bugfix_loop"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/development_bugfix_loop/latest.json"

#: Bounded length for free-text fields.
MAX_DETAIL_LEN: Final[int] = 500
MAX_NOTES_LEN: Final[int] = 1000
MAX_PATH_LEN: Final[int] = 256
MAX_FAILURES: Final[int] = 1000

#: Wrapper-level note vocabulary.
NOTE_INPUT_ABSENT: Final[str] = "input_absent"
NOTE_INPUT_EMPTY: Final[str] = "input_empty"
NOTE_CANDIDATES_PRESENT: Final[str] = "candidates_present"

#: Forbidden tokens in any acceptance-criteria template — pinned by
#: tests. The module's only safe templates are constructed from this
#: closed-vocabulary set; the test asserts the closed set never
#: contains a weakening token.
FORBIDDEN_ACCEPTANCE_TOKENS: Final[tuple[str, ...]] = (
    "skip",
    "xfail",
    "pytest.mark.skip",
    "pytest.mark.xfail",
    "remove pin",
    "weaken",
    "relax",
    "disable",
)

# ---------------------------------------------------------------------------
# Per-failure-class safe acceptance-criteria templates.
# Operator-extensible only via code review. None of these strings
# may match a FORBIDDEN_ACCEPTANCE_TOKENS entry; pinned by tests.
# ---------------------------------------------------------------------------

ACCEPTANCE_TEMPLATES: Final[dict[str, tuple[str, ...]]] = {
    "unit_test": (
        "reproduce the failure deterministically",
        "fix the root cause without changing assertions",
        "rerun the failing test until green",
        "rerun the broader unit suite",
    ),
    "smoke_test": (
        "reproduce the smoke failure deterministically",
        "fix the root cause without changing assertions",
        "rerun smoke and confirm green",
    ),
    "regression_test": (
        "reproduce the regression deterministically",
        "fix the root cause without removing pins",
        "rerun the regression test until green",
        "confirm pin still asserts the historical guarantee",
    ),
    "lint": (
        "address the lint finding at its source",
        "rerun the lint check until green",
    ),
    "typecheck": (
        "fix the type error at its source",
        "rerun mypy narrow until green",
    ),
    "governance_lint": (
        "fix the governance-lint finding at its source",
        "rerun governance_lint until OK",
    ),
    "frozen_hash": (
        "operator confirms whether this drift is intentional",
        "if drift is unintentional, revert to the byte-stable state",
        "if drift is intentional, follow the operator-authored frozen-hash rotation flow",
    ),
    "hook": (
        "operator reviews whether the hook is correctly tuned",
        "fix the underlying cause without bypassing the hook",
    ),
    "ci_workflow": (
        "ci_guardian reviews the workflow change required",
        "fix root cause through a ci-guardian-authored workflow PR",
    ),
    "unknown": (
        "operator triages the failure",
        "classify the failure into a known failure_class",
    ),
}

#: Suggested primary agent role per failure class (closed mapping).
ROLE_BY_FAILURE_CLASS: Final[dict[str, str]] = {
    "unit_test": "test_agent",
    "smoke_test": "test_agent",
    "regression_test": "test_agent",
    "lint": "implementation_agent",
    "typecheck": "implementation_agent",
    "governance_lint": "architecture_guardian",
    "frozen_hash": "human_operator",
    "hook": "architecture_guardian",
    "ci_workflow": "ci_guardian",
    "unknown": "human_operator",
}

#: Suggested A8 category per failure class (closed mapping).
CATEGORY_BY_FAILURE_CLASS: Final[dict[str, str]] = {
    "unit_test": "test",
    "smoke_test": "test",
    "regression_test": "test",
    "lint": "refactor",
    "typecheck": "refactor",
    "governance_lint": "governance",
    "frozen_hash": "governance",
    "hook": "governance",
    "ci_workflow": "ci",
    "unknown": "refactor",
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


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _normalize_path(p: str) -> str:
    """Repo-relative POSIX path. Mirrors
    ``reporting.execution_authority._normalize`` so that ``.claude/``
    and ``.github/`` paths retain their leading dot."""
    if not p:
        return ""
    forward = p.replace("\\", "/")
    if forward.startswith("./"):
        return forward[2:]
    if forward.startswith("."):
        return forward
    return forward.lstrip("/")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _coerce_count(value: Any) -> int:
    if isinstance(value, bool):
        return 1
    if isinstance(value, int) and value >= 1:
        if value > 10**9:  # bounded
            return 10**9
        return value
    return 1


def _deterministic_candidate_id(
    failure_class: str, target_path: str, message_digest: str
) -> str:
    h = hashlib.sha256()
    h.update(failure_class.encode("utf-8"))
    h.update(b"\x1f")
    h.update(target_path.encode("utf-8"))
    h.update(b"\x1f")
    h.update(message_digest.encode("utf-8"))
    return "bug_" + h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------


def _classify_target_to_scope(
    target_path_category: str,
    *,
    failure_class: str,
    authority_decision: str,
) -> tuple[str, bool, str]:
    """Map (target_path_category, authority_decision) to
    (bugfix_scope, human_needed, human_needed_reason)."""
    if target_path_category == "frozen_contract":
        return ("frozen_contract", True, "frozen_contract_change")
    if target_path_category == "live_path":
        return ("live_path", True, "capital_or_live_execution_related")
    if target_path_category in {
        "claude_governance_hook",
        "dashboard_wiring",
        "canonical_policy_doc",
        "canonical_roadmap",
        "branch_protection_config",
        "deploy_script",
    }:
        return ("protected_path", True, "protected_governance_change")
    if target_path_category == "ci_workflow":
        return ("ci_only", True, "protected_governance_change")
    if authority_decision == ea.DECISION_PERMANENTLY_DENIED:
        return ("protected_path", True, "protected_governance_change")
    if authority_decision == ea.DECISION_NEEDS_HUMAN:
        return ("requires_architecture_review", True, "ambiguous_scope")
    if target_path_category == "other":
        return ("requires_architecture_review", True, "ambiguous_scope")
    if failure_class == "frozen_hash":
        return ("frozen_contract", True, "frozen_contract_change")
    if failure_class == "ci_workflow":
        return ("ci_only", True, "protected_governance_change")
    return ("bounded_in_repo", False, "none")


def _safe_acceptance_template(failure_class: str) -> list[str]:
    return list(ACCEPTANCE_TEMPLATES.get(failure_class, ACCEPTANCE_TEMPLATES["unknown"]))


def _suggested_status_for(human_needed: bool, repeat_count: int) -> str:
    if human_needed or repeat_count >= REPEATED_FAILURE_THRESHOLD:
        return "human_needed"
    return "proposed"


# ---------------------------------------------------------------------------
# Failure parsing
# ---------------------------------------------------------------------------


def _parse_failure(
    raw: Any, *, line_index: int
) -> tuple[dict[str, Any] | None, list[str]]:
    """Project a raw failure record onto the closed schema.

    Returns ``(candidate, warnings)``. Invalid records are dropped
    with a warning, never raised."""
    warnings: list[str] = []
    if not isinstance(raw, dict):
        warnings.append(f"failure_{line_index}_not_an_object")
        return None, warnings

    fc = raw.get("failure_class")
    if fc not in FAILURE_CLASSES:
        warnings.append(f"failure_{line_index}_invalid_failure_class")
        return None, warnings

    target_raw = raw.get("target_path")
    if not isinstance(target_raw, str) or not target_raw.strip():
        target_path = ""
    else:
        target_path = _normalize_path(_bounded_str(target_raw, MAX_PATH_LEN))

    message_digest = _bounded_str(raw.get("message_digest"), 64)
    if not message_digest:
        # Synthesize a deterministic placeholder digest so identical
        # input produces identical candidate_id even when the operator
        # does not pre-hash.
        h = hashlib.sha256()
        h.update(_bounded_str(raw.get("detail"), MAX_DETAIL_LEN).encode("utf-8"))
        message_digest = h.hexdigest()[:24]

    severity_raw = raw.get("severity")
    if isinstance(severity_raw, str) and severity_raw in INPUT_SEVERITIES:
        severity = severity_raw
    else:
        severity = "unknown"

    repeat_count = _coerce_count(raw.get("occurrence_count"))

    first_seen = _bounded_str(raw.get("first_seen_utc"), 32)
    last_seen = _bounded_str(raw.get("last_seen_utc"), 32)

    detail = _bounded_str(raw.get("detail"), MAX_DETAIL_LEN)

    # Authority classification — never reads the file at target_path.
    decision = ea.classify(
        action_type="file_edit",
        target_path=target_path or None,
        risk_class=ea.RISK_UNKNOWN if severity == "unknown" else _severity_to_risk(severity),
    )
    target_path_category = decision.target_path_category

    bugfix_scope, human_needed, human_reason = _classify_target_to_scope(
        target_path_category,
        failure_class=fc,
        authority_decision=decision.decision,
    )

    # Repeated-failure escalation may flip a non-human-needed
    # candidate to human_needed.
    if not human_needed and repeat_count >= REPEATED_FAILURE_THRESHOLD:
        human_needed = True
        human_reason = "repeated_validation_failure"

    suggested_status = _suggested_status_for(human_needed, repeat_count)

    candidate_id = _deterministic_candidate_id(fc, target_path, message_digest)

    candidate: dict[str, Any] = {
        "candidate_id": candidate_id,
        "failure_class": fc,
        "target_path": target_path,
        "target_path_category": target_path_category,
        "bugfix_scope": bugfix_scope,
        "suggested_status": suggested_status,
        "suggested_required_agent_role": ROLE_BY_FAILURE_CLASS[fc],
        "suggested_category": CATEGORY_BY_FAILURE_CLASS[fc],
        "human_needed": human_needed,
        "human_needed_reason": human_reason,
        "execution_authority_decision": decision.decision,
        "execution_authority_reason": decision.reason,
        "repeat_count": repeat_count,
        "first_seen_utc": first_seen,
        "last_seen_utc": last_seen,
        "severity": severity,
        "acceptance_criteria_template": _safe_acceptance_template(fc),
        "notes": detail,
        "created_at_placeholder": ITEM_TIME_PLACEHOLDER,
        "updated_at_placeholder": ITEM_TIME_PLACEHOLDER,
    }
    return candidate, warnings


def _severity_to_risk(severity: str) -> str:
    if severity == "low":
        return ea.RISK_LOW
    if severity == "medium":
        return ea.RISK_MEDIUM
    if severity == "high":
        return ea.RISK_HIGH
    return ea.RISK_UNKNOWN


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_failure_class": {fc: 0 for fc in FAILURE_CLASSES},
        "by_bugfix_scope": {s: 0 for s in BUGFIX_SCOPES},
        "by_suggested_status": {s: 0 for s in SUGGESTED_STATUSES},
        "human_needed": 0,
        "repeated_failure": 0,
        "out_of_scope": 0,
        "ready_for_operator_promotion": 0,
        "requiring_human_operator": 0,
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        counts["by_failure_class"][row["failure_class"]] += 1
        counts["by_bugfix_scope"][row["bugfix_scope"]] += 1
        counts["by_suggested_status"][row["suggested_status"]] += 1
        if row["human_needed"]:
            counts["human_needed"] += 1
            counts["requiring_human_operator"] += 1
        else:
            counts["ready_for_operator_promotion"] += 1
        if row["repeat_count"] >= REPEATED_FAILURE_THRESHOLD:
            counts["repeated_failure"] += 1
        if row["bugfix_scope"] == "out_of_scope":
            counts["out_of_scope"] += 1
    return counts


def collect_snapshot(
    *,
    failure_input_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic bugfix-loop snapshot from the failure
    summary contract."""
    fp = failure_input_path if failure_input_path is not None else DEFAULT_INPUT_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    payload = _read_json(fp)
    input_present = payload is not None

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    if input_present:
        raw_failures = (payload or {}).get("failures")
        if not isinstance(raw_failures, list):
            warnings.append("input_failures_not_a_list")
            raw_failures = []
        if len(raw_failures) > MAX_FAILURES:
            warnings.append(f"input_failures_truncated_at_{MAX_FAILURES}")
            raw_failures = raw_failures[:MAX_FAILURES]
        for idx, raw in enumerate(raw_failures, start=1):
            cand, warns = _parse_failure(raw, line_index=idx)
            warnings.extend(warns)
            if cand is not None:
                rows.append(cand)

    # Collapse duplicates by candidate_id; keep the row with the
    # highest repeat_count.
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = row["candidate_id"]
        if cid in by_id:
            existing = by_id[cid]
            if row["repeat_count"] > existing["repeat_count"]:
                by_id[cid] = row
        else:
            by_id[cid] = row
    rows = list(by_id.values())

    rows.sort(key=lambda r: r["candidate_id"])

    if not input_present:
        note = NOTE_INPUT_ABSENT
    elif not rows:
        note = NOTE_INPUT_EMPTY
    else:
        note = NOTE_CANDIDATES_PRESENT

    counts = _aggregate_counts(rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_bugfix_loop",
        "generated_at_utc": ts,
        "failure_input_path": str(fp),
        "failure_input_present": input_present,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "failure_classes": list(FAILURE_CLASSES),
            "bugfix_scopes": list(BUGFIX_SCOPES),
            "suggested_statuses": list(SUGGESTED_STATUSES),
            "input_severities": list(INPUT_SEVERITIES),
            "agent_roles": list(dwq.AGENT_ROLES),
            "categories": list(dwq.CATEGORIES),
            "human_needed_reasons": list(dwq.HUMAN_NEEDED_REASONS),
            "risk_levels": list(ea.RISK_CLASSES),
        },
        "counts": counts,
        "candidates": rows,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "queue_module_version": dwq.MODULE_VERSION,
        "discipline_invariants": {
            "writes_to_seed_jsonl": False,
            "writes_to_bugfix_seed_jsonl": False,
            "auto_creates_branches": False,
            "auto_opens_prs": False,
            "auto_modifies_code": False,
            "operator_promotion_required": True,
        },
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_bugfix_loop._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_bugfix_loop.", suffix=".tmp", dir=str(path.parent)
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
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_bugfix_loop",
        description=(
            "Read-only intake module for routine failure summaries. "
            "Emits bugfix-candidate proposals to "
            "logs/development_bugfix_loop/latest.json. Mutates "
            "nothing; never writes to seed.jsonl or bugfix_seed.jsonl. "
            "Operator promotion is a separate manual action."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_bugfix_loop/latest.json "
            "(stdout only)."
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
