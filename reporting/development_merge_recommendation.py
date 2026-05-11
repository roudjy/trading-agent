"""A23 — Merge Recommendation (read-only projector).

Pure stdlib-only projector that joins:

* the A22 PR-lifecycle observer artefact at
  ``logs/development_pr_lifecycle_observer/latest.json``;
* the N3a mobile-approval-inbox artefact at
  ``logs/mobile_approval_inbox/latest.json``;

…and emits a closed-vocabulary **recommendation** record per open
PR at ``logs/development_merge_recommendation/latest.json``.

A23 is the **recommendation surface** — not the execution surface.
It NEVER merges any PR. It NEVER calls ``gh``. It NEVER opens a
network socket. It NEVER mints or verifies an approval token. The
output is a deterministic, bounded report the operator (or a future
N4/N5 surface, separately authorised) can consult before deciding
to act.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.development_pr_lifecycle_observer``
  (read-only) + ``reporting.mobile_approval_inbox`` (read-only) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* Atomic write only under
  ``logs/development_merge_recommendation/...``.
* Per-row schema is closed and exact. Bounded scalars only — no
  PR body text, no diff, no commit message.
* The recommendation NEVER carries a decision verb like ``approve``
  / ``merge`` / ``deploy`` in any rendered scalar. The closed
  vocabulary uses ``recommend_human_merge`` rather than
  ``approve_merge`` to make this unambiguous.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.
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

from reporting import development_pr_lifecycle_observer as a22
from reporting import mobile_approval_inbox as n3a
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A23"
REPORT_KIND: Final[str] = "development_merge_recommendation"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed recommendation-action vocabulary. NONE of the values
#: contains the literal token ``approve`` / ``merge`` / ``deploy``
#: as a verb — A23 makes recommendations to the *operator*, not to
#: any agent that could act. Pinned by source-text test.
RECOMMENDATION_ACTIONS: Final[tuple[str, ...]] = (
    "recommend_human_merge",
    "recommend_human_review",
    "recommend_no_action",
    "recommend_update_branch",
    "recommend_hold",
)

#: Closed recommendation-reason vocabulary.
RECOMMENDATION_REASONS: Final[tuple[str, ...]] = (
    # recommend_human_merge
    "pr_clean_and_no_blocking_inbox",
    # recommend_human_review
    "pr_clean_but_inbox_has_blocked_attention",
    "pr_clean_but_inbox_has_critical_attention",
    "pr_clean_but_inbox_has_needs_review",
    # recommend_no_action
    "pr_closed_or_merged",
    "pr_open_but_draft",
    # recommend_update_branch
    "pr_behind_base_branch",
    # recommend_hold
    "pr_blocked_or_dirty",
    "pr_unstable_checks",
    "pr_unknown_state",
    "no_upstream_signal",
    "ineligible_pr_shape",
)

#: Closed validation-warning vocabulary.
VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "pr_lifecycle_observer_absent",
    "pr_lifecycle_observer_unparseable",
    "mobile_approval_inbox_absent",
    "mobile_approval_inbox_unparseable",
    "no_open_prs",
)

#: Per-row schema, exact and ordered.
RECOMMENDATION_ROW_KEYS: Final[tuple[str, ...]] = (
    "recommendation_id",
    "pr_number",
    "head_sha",
    "head_ref",
    "base_ref",
    "observer_classification",
    "inbox_blocked_count",
    "inbox_critical_count",
    "inbox_needs_review_count",
    "recommendation_action",
    "recommendation_reason",
    "evaluated_at",
)

#: Wrapper-level note vocabulary.
NOTE_NO_OBSERVER: Final[str] = "pr_lifecycle_observer_absent"
NOTE_NO_INBOX: Final[str] = "mobile_approval_inbox_absent"
NOTE_NO_OPEN_PRS: Final[str] = "no_open_prs"
NOTE_RECOMMENDATIONS_PRESENT: Final[str] = "recommendations_present"

#: Maximum rows kept in any single snapshot.
MAX_RECOMMENDATION_ROWS: Final[int] = 64

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_merge_recommendation"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_merge_recommendation/latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/development_merge_recommendation/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "calls_gh_cli": False,
    "merges_or_deploys": False,
    "mints_approval_token": False,
    "verifies_approval_token": False,
    "executes_approve_or_reject": False,
    "sends_real_push": False,
    "registers_flask_blueprint": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "writes_to_seed_jsonl": False,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
    "diagnostics_do_not_trade": True,
    "no_approval_from_notification_click_alone": True,
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


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _bounded(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len]


def _recommendation_id(pr_number: int, head_sha: str) -> str:
    """Stable recommendation id derived from PR number + head SHA.

    The id changes whenever the head advances (which is the right
    semantics — a new head means the recommendation needs
    re-evaluation against the updated branch).
    """
    sha_prefix = head_sha[:12] if isinstance(head_sha, str) else ""
    return f"mr_{pr_number}_{sha_prefix}"


# ---------------------------------------------------------------------------
# Recommendation derivation (closed table; first match wins)
# ---------------------------------------------------------------------------


def evaluate_pr(
    pr_row: dict[str, Any],
    *,
    inbox_blocked_count: int,
    inbox_critical_count: int,
    inbox_needs_review_count: int,
) -> tuple[str, str]:
    """Closed-table mapping from one A22 observer row + inbox
    attention counts to a recommendation ``(action, reason)``.

    Priority order (first match wins):

    1. PR is closed/merged → recommend_no_action
    2. PR is draft → recommend_no_action
    3. PR is blocked/dirty → recommend_hold
    4. PR is unstable → recommend_hold
    5. PR is behind base → recommend_update_branch
    6. PR has ineligible/unknown shape → recommend_hold
    7. PR is clean AND inbox has critical_attention →
       recommend_human_review
    8. PR is clean AND inbox has blocked_attention →
       recommend_human_review
    9. PR is clean AND inbox has needs_review →
       recommend_human_review
    10. PR is clean AND inbox is clean → recommend_human_merge
        (final hand-off to a human; NOT an autonomous merge)
    11. default-deny → recommend_hold / no_upstream_signal
    """
    if not isinstance(pr_row, dict):
        return ("recommend_hold", "ineligible_pr_shape")

    classification = pr_row.get("observer_classification")

    if classification == "closed_or_merged":
        return ("recommend_no_action", "pr_closed_or_merged")
    if classification == "open_draft":
        return ("recommend_no_action", "pr_open_but_draft")
    if classification == "open_blocked_or_dirty":
        return ("recommend_hold", "pr_blocked_or_dirty")
    if classification == "open_unstable":
        return ("recommend_hold", "pr_unstable_checks")
    if classification == "open_behind_base":
        return ("recommend_update_branch", "pr_behind_base_branch")
    if classification in ("open_unknown", "ineligible_shape"):
        return ("recommend_hold", "pr_unknown_state")

    if classification == "open_clean_mergeable":
        if inbox_critical_count > 0:
            return (
                "recommend_human_review",
                "pr_clean_but_inbox_has_critical_attention",
            )
        if inbox_blocked_count > 0:
            return (
                "recommend_human_review",
                "pr_clean_but_inbox_has_blocked_attention",
            )
        if inbox_needs_review_count > 0:
            return (
                "recommend_human_review",
                "pr_clean_but_inbox_has_needs_review",
            )
        return ("recommend_human_merge", "pr_clean_and_no_blocking_inbox")

    return ("recommend_hold", "no_upstream_signal")


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------


def _build_row(
    pr_row: dict[str, Any],
    *,
    inbox_counts: dict[str, int],
    evaluated_at: str,
) -> dict[str, Any] | None:
    if not isinstance(pr_row, dict):
        return None
    try:
        pr_number = int(pr_row.get("pr_number") or 0)
    except (TypeError, ValueError):
        pr_number = 0
    if pr_number == 0:
        return None

    blocked = int(inbox_counts.get("blocked_attention") or 0)
    critical = int(inbox_counts.get("critical_attention") or 0)
    needs_review = int(inbox_counts.get("needs_review") or 0)
    action, reason = evaluate_pr(
        pr_row,
        inbox_blocked_count=blocked,
        inbox_critical_count=critical,
        inbox_needs_review_count=needs_review,
    )

    row: dict[str, Any] = {
        "recommendation_id": _recommendation_id(
            pr_number, str(pr_row.get("head_sha") or "")
        ),
        "pr_number": pr_number,
        "head_sha": _bounded(pr_row.get("head_sha"), 64),
        "head_ref": _bounded(pr_row.get("head_ref"), 200),
        "base_ref": _bounded(pr_row.get("base_ref"), 200),
        "observer_classification": str(pr_row.get("observer_classification") or ""),
        "inbox_blocked_count": blocked,
        "inbox_critical_count": critical,
        "inbox_needs_review_count": needs_review,
        "recommendation_action": action,
        "recommendation_reason": reason,
        "evaluated_at": evaluated_at,
    }
    assert set(row.keys()) == set(RECOMMENDATION_ROW_KEYS)
    return row


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_recommendation_action": {a: 0 for a in RECOMMENDATION_ACTIONS},
        "by_recommendation_reason": {r: 0 for r in RECOMMENDATION_REASONS},
        "by_observer_classification": {
            c: 0 for c in a22.OBSERVER_CLASSIFICATIONS
        },
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        action = row.get("recommendation_action")
        if action in counts["by_recommendation_action"]:
            counts["by_recommendation_action"][action] += 1
        reason = row.get("recommendation_reason")
        if reason in counts["by_recommendation_reason"]:
            counts["by_recommendation_reason"][reason] += 1
        cls = row.get("observer_classification")
        if cls in counts["by_observer_classification"]:
            counts["by_observer_classification"][cls] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    pr_observer_artifact_path: Path | None = None,
    inbox_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic recommendation snapshot."""
    pp = (
        pr_observer_artifact_path
        if pr_observer_artifact_path is not None
        else a22.ARTIFACT_LATEST
    )
    ip = (
        inbox_artifact_path
        if inbox_artifact_path is not None
        else n3a.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    observer_payload = _read_json(pp)
    inbox_payload = _read_json(ip)
    warnings: list[str] = []

    if observer_payload is None:
        warnings.append("pr_lifecycle_observer_absent")
    elif not isinstance(observer_payload, dict):
        warnings.append("pr_lifecycle_observer_unparseable")
        observer_payload = None

    if inbox_payload is None:
        warnings.append("mobile_approval_inbox_absent")
    elif not isinstance(inbox_payload, dict):
        warnings.append("mobile_approval_inbox_unparseable")
        inbox_payload = None

    # Read PR rows from observer.
    pr_rows: list[dict[str, Any]] = []
    if isinstance(observer_payload, dict):
        raw = observer_payload.get("rows")
        if isinstance(raw, list):
            pr_rows = [r for r in raw if isinstance(r, dict)]

    # Read inbox attention counts.
    inbox_counts: dict[str, int] = {
        "blocked_attention": 0,
        "critical_attention": 0,
        "needs_review": 0,
    }
    if isinstance(inbox_payload, dict):
        upstream_counts = inbox_payload.get("counts") or {}
        if isinstance(upstream_counts, dict):
            inbox_counts["blocked_attention"] = int(
                upstream_counts.get("blocked_attention") or 0
            )
            inbox_counts["critical_attention"] = int(
                upstream_counts.get("critical_attention") or 0
            )
            inbox_counts["needs_review"] = int(
                upstream_counts.get("needs_review") or 0
            )

    rows: list[dict[str, Any]] = []
    for pr_row in pr_rows:
        if len(rows) >= MAX_RECOMMENDATION_ROWS:
            break
        row = _build_row(pr_row, inbox_counts=inbox_counts, evaluated_at=ts)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: (r["pr_number"], r["head_sha"]))

    if not rows:
        warnings.append("no_open_prs")
        note = NOTE_NO_OPEN_PRS
        if observer_payload is None:
            note = NOTE_NO_OBSERVER
        elif inbox_payload is None:
            note = NOTE_NO_INBOX
    else:
        note = NOTE_RECOMMENDATIONS_PRESENT

    counts = _aggregate_counts(rows)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "pr_observer_artifact_path": str(pp),
        "pr_observer_artifact_available": observer_payload is not None,
        "inbox_artifact_path": str(ip),
        "inbox_artifact_available": inbox_payload is not None,
        "max_recommendation_rows": MAX_RECOMMENDATION_ROWS,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "recommendation_actions": list(RECOMMENDATION_ACTIONS),
            "recommendation_reasons": list(RECOMMENDATION_REASONS),
            "observer_classifications": list(a22.OBSERVER_CLASSIFICATIONS),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "recommendation_row_keys": list(RECOMMENDATION_ROW_KEYS),
        },
        "counts": counts,
        "rows": rows,
        "pr_lifecycle_observer_module_version": a22.MODULE_VERSION,
        "mobile_approval_inbox_module_version": n3a.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_merge_recommendation._atomic_write_json refuses "
            f"non-recommendation-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_merge_recommendation.",
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
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_merge_recommendation",
        description=(
            "A23 Merge Recommendation. Read-only deterministic "
            "projector that joins A22 PR observer + N3a mobile "
            "approval inbox into a closed-vocabulary recommendation "
            "record. Recommends only; never merges; never calls gh."
        ),
    )
    p.add_argument(
        "--indent", type=int, default=2, help="JSON indent (0 for compact)."
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_merge_recommendation/latest.json "
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
