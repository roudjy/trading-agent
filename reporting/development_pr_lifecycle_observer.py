"""A22 — Draft PR lifecycle observer (read-only projector).

Pure stdlib-only projector that reads the existing GitHub PR
lifecycle digest at ``logs/github_pr_lifecycle/latest.json`` and
emits a closed-vocabulary per-PR summary record under
``logs/development_pr_lifecycle_observer/latest.json``.

A22 is a **strict read-only observer**. It does not call the ``gh``
CLI itself, opens no socket, mutates no PR, comments on no PR,
merges nothing. The upstream digest is produced by the existing
``reporting.github_pr_lifecycle`` module (which does call ``gh``);
A22 is decoupled from that production path so the observer's own
test surface contains zero subprocess / network code.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.agent_audit_summary.assert_no_secrets``
  (read-only redactor guard). The module imports
  ``reporting.github_pr_lifecycle`` only for module-version pinning;
  it never calls any function from that module.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* Atomic write only under
  ``logs/development_pr_lifecycle_observer/...``.
* Per-row schema is closed and exact. Bounded scalars only — no PR
  body text, no diff content, no commit messages.
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

from reporting import github_pr_lifecycle as _gh_lifecycle  # for MODULE_VERSION pin only
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A22"
REPORT_KIND: Final[str] = "development_pr_lifecycle_observer"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed PR-state vocabulary as observed in the upstream digest.
PR_STATES: Final[tuple[str, ...]] = (
    "OPEN",
    "CLOSED",
    "MERGED",
    "DRAFT",
    "UNKNOWN",
)

#: Closed merge-state-status vocabulary (mirrors gh GraphQL).
MERGE_STATE_STATUSES: Final[tuple[str, ...]] = (
    "BEHIND",
    "BLOCKED",
    "CLEAN",
    "DIRTY",
    "DRAFT",
    "HAS_HOOKS",
    "UNKNOWN",
    "UNSTABLE",
)

#: Closed observer-classification vocabulary. A22 never *recommends*
#: a merge (that's A23 territory) — the classification is purely
#: descriptive of where the PR sits in its lifecycle.
OBSERVER_CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "open_clean_mergeable",
    "open_blocked_or_dirty",
    "open_behind_base",
    "open_draft",
    "open_unstable",
    "open_unknown",
    "closed_or_merged",
    "ineligible_shape",
)

#: Closed validation-warning vocabulary.
VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "upstream_digest_absent",
    "upstream_digest_unparseable",
    "upstream_provider_not_available",
    "upstream_pr_record_invalid",
)

#: Per-PR row schema, exact and ordered.
PR_ROW_KEYS: Final[tuple[str, ...]] = (
    "pr_number",
    "title",
    "head_ref",
    "head_sha",
    "base_ref",
    "state",
    "is_draft",
    "merge_state_status",
    "mergeable",
    "checks_summary",
    "author_login",
    "is_dependabot",
    "observer_classification",
    "url",
    "created_at",
    "updated_at",
)

#: Wrapper-level note vocabulary.
NOTE_NO_DIGEST: Final[str] = "upstream_digest_absent"
NOTE_PROVIDER_NOT_AVAILABLE: Final[str] = "upstream_provider_not_available"
NOTE_NO_PRS: Final[str] = "no_open_prs"
NOTE_PRS_PRESENT: Final[str] = "prs_present"

#: Bounded length for free-text scalars. No PR body, no diff, no
#: commit text in the artefact.
MAX_TITLE_LEN: Final[int] = 200
MAX_REF_LEN: Final[int] = 200
MAX_LOGIN_LEN: Final[int] = 64
MAX_URL_LEN: Final[int] = 300

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_pr_lifecycle_observer"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_pr_lifecycle_observer/latest.json"
)

#: Upstream digest produced by the (subprocess-using)
#: ``reporting.github_pr_lifecycle`` module. A22 reads this file
#: only — never invokes the upstream module.
UPSTREAM_DIGEST_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "github_pr_lifecycle" / "latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/development_pr_lifecycle_observer/"


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "calls_gh_cli": False,
    "merges_or_comments_on_prs": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "writes_to_seed_jsonl": False,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
    "diagnostics_do_not_trade": True,
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


# ---------------------------------------------------------------------------
# Per-PR classification
# ---------------------------------------------------------------------------


def classify_pr(row: dict[str, Any]) -> str:
    """Closed-table classification. Returns a value from
    :data:`OBSERVER_CLASSIFICATIONS`. Pure; never calls the network.
    """
    if not isinstance(row, dict):
        return "ineligible_shape"

    state = str(row.get("state") or "UNKNOWN").upper()
    if state not in PR_STATES:
        state = "UNKNOWN"

    if state in {"CLOSED", "MERGED"}:
        return "closed_or_merged"

    is_draft = bool(row.get("is_draft") or row.get("isDraft"))
    if is_draft or state == "DRAFT":
        return "open_draft"

    merge_state = (
        str(row.get("merge_state_status") or row.get("mergeStateStatus") or "UNKNOWN").upper()
    )
    if merge_state not in MERGE_STATE_STATUSES:
        merge_state = "UNKNOWN"

    if merge_state == "CLEAN":
        return "open_clean_mergeable"
    if merge_state in {"BLOCKED", "DIRTY", "HAS_HOOKS"}:
        return "open_blocked_or_dirty"
    if merge_state == "BEHIND":
        return "open_behind_base"
    if merge_state == "UNSTABLE":
        return "open_unstable"
    if merge_state == "DRAFT":
        return "open_draft"
    return "open_unknown"


# ---------------------------------------------------------------------------
# Per-PR row construction
# ---------------------------------------------------------------------------


def _build_row(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Coerce one upstream PR record into the closed observer schema.
    Returns ``(row, warning)``."""
    if not isinstance(raw, dict):
        return None, "upstream_pr_record_invalid"

    # Tolerate both snake_case and camelCase from gh GraphQL fields.
    pr_number = raw.get("pr_number") or raw.get("number")
    try:
        pr_number_int = int(pr_number) if pr_number is not None else 0
    except (TypeError, ValueError):
        pr_number_int = 0

    state = str(raw.get("state") or "UNKNOWN").upper()
    if state not in PR_STATES:
        state = "UNKNOWN"

    merge_state = (
        str(raw.get("merge_state_status") or raw.get("mergeStateStatus") or "UNKNOWN").upper()
    )
    if merge_state not in MERGE_STATE_STATUSES:
        merge_state = "UNKNOWN"

    head_ref = _bounded(
        raw.get("head_ref") or raw.get("headRefName") or "", MAX_REF_LEN
    )
    head_sha = _bounded(
        raw.get("head_sha") or raw.get("headRefOid") or "", MAX_REF_LEN
    )
    base_ref = _bounded(
        raw.get("base_ref") or raw.get("baseRefName") or "main", MAX_REF_LEN
    )
    title = _bounded(raw.get("title") or "", MAX_TITLE_LEN)

    author_raw = raw.get("author")
    if isinstance(author_raw, dict):
        login = _bounded(author_raw.get("login") or "", MAX_LOGIN_LEN)
    else:
        login = _bounded(raw.get("author_login") or "", MAX_LOGIN_LEN)
    is_dependabot = bool(login.lower().startswith("dependabot"))

    is_draft = bool(raw.get("is_draft") or raw.get("isDraft"))
    mergeable = (
        str(raw.get("mergeable") or "").upper() if raw.get("mergeable") else ""
    )
    checks_summary = _bounded(
        str(raw.get("checks_summary") or raw.get("statusCheckRollupState") or ""),
        64,
    )
    url = _bounded(raw.get("url") or "", MAX_URL_LEN)
    created_at = _bounded(raw.get("created_at") or raw.get("createdAt") or "", 32)
    updated_at = _bounded(raw.get("updated_at") or raw.get("updatedAt") or "", 32)

    classification = classify_pr(
        {
            "state": state,
            "is_draft": is_draft,
            "merge_state_status": merge_state,
        }
    )

    row: dict[str, Any] = {
        "pr_number": pr_number_int,
        "title": title,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "base_ref": base_ref,
        "state": state,
        "is_draft": is_draft,
        "merge_state_status": merge_state,
        "mergeable": mergeable,
        "checks_summary": checks_summary,
        "author_login": login,
        "is_dependabot": is_dependabot,
        "observer_classification": classification,
        "url": url,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    assert set(row.keys()) == set(PR_ROW_KEYS)
    return row, None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "open_total": 0,
        "open_clean_mergeable": 0,
        "open_blocked_or_dirty": 0,
        "open_behind_base": 0,
        "open_draft": 0,
        "open_unstable": 0,
        "open_unknown": 0,
        "closed_or_merged": 0,
        "ineligible_shape": 0,
        "by_observer_classification": {
            c: 0 for c in OBSERVER_CLASSIFICATIONS
        },
        "by_state": {s: 0 for s in PR_STATES},
        "by_merge_state_status": {m: 0 for m in MERGE_STATE_STATUSES},
        "dependabot_count": 0,
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for r in rows:
        cls = r.get("observer_classification")
        if cls in counts:
            counts[cls] += 1
        if cls in counts["by_observer_classification"]:
            counts["by_observer_classification"][cls] += 1
        if cls and cls.startswith("open_"):
            counts["open_total"] += 1
        state = r.get("state")
        if isinstance(state, str) and state in counts["by_state"]:
            counts["by_state"][state] += 1
        ms = r.get("merge_state_status")
        if isinstance(ms, str) and ms in counts["by_merge_state_status"]:
            counts["by_merge_state_status"][ms] += 1
        if r.get("is_dependabot"):
            counts["dependabot_count"] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    upstream_digest_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic observer snapshot."""
    up = (
        upstream_digest_path
        if upstream_digest_path is not None
        else UPSTREAM_DIGEST_PATH
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    payload = _read_json(up)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    upstream_provider_status = ""
    upstream_module_version = ""

    if payload is None:
        warnings.append("upstream_digest_absent")
        note = NOTE_NO_DIGEST
    elif not isinstance(payload, dict):
        warnings.append("upstream_digest_unparseable")
        note = NOTE_NO_DIGEST
    else:
        upstream_provider_status = str(
            payload.get("provider_status") or ""
        )
        upstream_module_version = str(payload.get("module_version") or "")
        if upstream_provider_status == "not_available":
            warnings.append("upstream_provider_not_available")
            note = NOTE_PROVIDER_NOT_AVAILABLE
        else:
            note = NOTE_NO_PRS
        prs_raw = payload.get("prs")
        if isinstance(prs_raw, list):
            for raw in prs_raw:
                row, warn = _build_row(raw)
                if warn is not None:
                    warnings.append(warn)
                if row is not None:
                    rows.append(row)
        if rows:
            note = NOTE_PRS_PRESENT

    rows.sort(key=lambda r: (r["pr_number"], r["head_sha"]))
    counts = _aggregate_counts(rows)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "upstream_digest_path": str(up),
        "upstream_digest_available": payload is not None,
        "upstream_provider_status": upstream_provider_status,
        "upstream_module_version": upstream_module_version,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "pr_states": list(PR_STATES),
            "merge_state_statuses": list(MERGE_STATE_STATUSES),
            "observer_classifications": list(OBSERVER_CLASSIFICATIONS),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "pr_row_keys": list(PR_ROW_KEYS),
        },
        "counts": counts,
        "rows": rows,
        "github_pr_lifecycle_module_version": _gh_lifecycle.MODULE_VERSION,
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
            "development_pr_lifecycle_observer._atomic_write_json refuses "
            f"non-observer-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_pr_lifecycle_observer.",
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
        prog="python -m reporting.development_pr_lifecycle_observer",
        description=(
            "A22 PR lifecycle observer. Read-only deterministic "
            "projector of logs/github_pr_lifecycle/latest.json. "
            "Never calls gh; never merges; never comments."
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
            "logs/development_pr_lifecycle_observer/latest.json "
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
