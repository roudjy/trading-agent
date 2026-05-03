"""Autonomy throughput / observability metrics (v3.15.15.25).

A deterministic, stdlib-only metrics collector that aggregates
the JSON artifacts produced by the existing reporting modules
(workloop_runtime, recurring_maintenance, proposal_queue,
approval_inbox, github_pr_lifecycle, execute_safe_controls,
agent_audit_summary) into a single read-only digest. The digest
answers the operator-burden / reliability / safety / throughput
questions enumerated in the v3.15.15.25 brief without expanding
any execution authority.

Hard guarantees
---------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* The collector NEVER writes to ``research/``, ``.claude/``,
  ``automation/``, ``execution/``, or any other governance-protected
  path. Output is limited to ``logs/autonomy_metrics/``.
* Writes are atomic (``tmp`` + ``os.replace``) and history is
  append-only.
* Output is run through narrow credential-value redaction
  (``sk-ant-`` / ``ghp_`` / ``github_pat_`` / ``AKIA`` /
  ``BEGIN PRIVATE KEY``); path-shaped strings are explicitly
  preserved so the operator can still see *what* the source was.
* Missing / malformed artifacts are COUNTED and reported under
  ``source_statuses`` — never silently coerced to "ok".
* The output is deterministic given a fixed set of input
  artifacts. There is no clock-derived field beyond the
  top-level ``generated_at_utc`` which the caller may pin via
  ``--frozen-utc`` for testing.
* ``high_or_unknown_executable_count`` is expected to be
  zero. A non-zero value flips ``final_recommendation`` to
  ``unsafe_state_detected``.

CLI
---

::

    python -m reporting.autonomy_metrics --collect
    python -m reporting.autonomy_metrics --status
    python -m reporting.autonomy_metrics --no-write

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from reporting import approval_policy as _approval_policy

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.15.27"
METRICS_VERSION: str = "v1"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "autonomy_metrics"

# v3.15.15.27 — stale-artifact threshold. A source whose
# ``generated_at_utc`` is older than this is counted as stale even
# though it parsed cleanly. Default 24 hours; the operator can
# override via the AUTONOMY_METRICS_STALE_THRESHOLD_SECONDS env var
# at collection time. The threshold is conservative on purpose —
# we want operators to notice when the workloop has stopped
# producing fresh artifacts, not to swamp them with churn.
STALE_THRESHOLD_SECONDS_DEFAULT: int = 24 * 3600


# ---------------------------------------------------------------------------
# Source artifact paths — kept narrow on purpose.
# ---------------------------------------------------------------------------


SOURCE_WORKLOOP_RUNTIME: Path = REPO_ROOT / "logs" / "workloop_runtime" / "latest.json"
SOURCE_WORKLOOP_RUNTIME_HISTORY: Path = (
    REPO_ROOT / "logs" / "workloop_runtime" / "history.jsonl"
)
SOURCE_RECURRING_MAINTENANCE: Path = (
    REPO_ROOT / "logs" / "recurring_maintenance" / "latest.json"
)
SOURCE_RECURRING_MAINTENANCE_HISTORY: Path = (
    REPO_ROOT / "logs" / "recurring_maintenance" / "history.jsonl"
)
SOURCE_PROPOSAL_QUEUE: Path = REPO_ROOT / "logs" / "proposal_queue" / "latest.json"
SOURCE_APPROVAL_INBOX: Path = REPO_ROOT / "logs" / "approval_inbox" / "latest.json"
SOURCE_PR_LIFECYCLE: Path = REPO_ROOT / "logs" / "github_pr_lifecycle" / "latest.json"
SOURCE_EXECUTE_SAFE_CONTROLS: Path = (
    REPO_ROOT / "logs" / "execute_safe_controls" / "latest.json"
)


# Source ordering controls determinism in the digest.
SOURCE_ORDER: tuple[tuple[str, str], ...] = (
    ("workloop_runtime", "logs/workloop_runtime/latest.json"),
    ("recurring_maintenance", "logs/recurring_maintenance/latest.json"),
    ("proposal_queue", "logs/proposal_queue/latest.json"),
    ("approval_inbox", "logs/approval_inbox/latest.json"),
    ("github_pr_lifecycle", "logs/github_pr_lifecycle/latest.json"),
    ("execute_safe_controls", "logs/execute_safe_controls/latest.json"),
)


# Source status enum.
STATE_OK: str = "ok"
STATE_MISSING: str = "missing"
STATE_MALFORMED: str = "malformed"
STATE_UNREADABLE: str = "unreadable"
STATE_NOT_AN_OBJECT: str = "not_an_object"

SOURCE_STATES: tuple[str, ...] = (
    STATE_OK,
    STATE_MISSING,
    STATE_MALFORMED,
    STATE_UNREADABLE,
    STATE_NOT_AN_OBJECT,
)


# Final recommendation enum.
REC_HEALTHY: str = "healthy"
REC_DEGRADED_MISSING: str = "degraded_missing_sources"
REC_DEGRADED_FAILURES: str = "degraded_failures"
REC_ACTION_REQUIRED: str = "action_required"
REC_UNSAFE: str = "unsafe_state_detected"
REC_NOT_AVAILABLE: str = "not_available"

FINAL_RECOMMENDATIONS: tuple[str, ...] = (
    REC_HEALTHY,
    REC_DEGRADED_MISSING,
    REC_DEGRADED_FAILURES,
    REC_ACTION_REQUIRED,
    REC_UNSAFE,
    REC_NOT_AVAILABLE,
)


# Trend window labels.
TREND_LAST_24H: str = "last_24h"
TREND_LAST_7D: str = "last_7d"
TREND_ALL_TIME: str = "all_time_from_available_history"


# ---------------------------------------------------------------------------
# Time + path helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _utcnow_dt() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0)


def _stale_threshold_from_env() -> int:
    """Return the staleness threshold in seconds, honouring the
    ``AUTONOMY_METRICS_STALE_THRESHOLD_SECONDS`` env var when set
    to a positive integer. Falls back to
    ``STALE_THRESHOLD_SECONDS_DEFAULT`` otherwise."""
    raw = os.environ.get("AUTONOMY_METRICS_STALE_THRESHOLD_SECONDS", "")
    try:
        v = int(raw)
        if v > 0:
            return v
    except (TypeError, ValueError):
        pass
    return STALE_THRESHOLD_SECONDS_DEFAULT


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return "missing"
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Source readers — never raise; missing / malformed → status entry
# ---------------------------------------------------------------------------


def _read_json_artifact(path: Path) -> dict[str, Any]:
    """Return a status envelope ``{state, reason, data}``. Always
    returns a dict; never raises."""
    if not path.exists():
        return {
            "state": STATE_MISSING,
            "reason": "missing",
            "data": None,
        }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {
            "state": STATE_UNREADABLE,
            "reason": f"unreadable: {type(e).__name__}",
            "data": None,
        }
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {
            "state": STATE_MALFORMED,
            "reason": f"malformed: {type(e).__name__}",
            "data": None,
        }
    if not isinstance(data, dict):
        return {
            "state": STATE_NOT_AN_OBJECT,
            "reason": "malformed: not_an_object",
            "data": None,
        }
    return {"state": STATE_OK, "reason": None, "data": data}


def _read_jsonl_history(path: Path, *, max_records: int = 5000) -> list[dict[str, Any]]:
    """Read a ``history.jsonl`` file best-effort. Lines that fail to
    parse are skipped silently — the history is informational only.
    Returns at most ``max_records`` parsed dict rows from the END
    (the most recent rows). Never raises."""
    if not path.exists() or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = text.splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-max_records:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


# ---------------------------------------------------------------------------
# Throughput / burden / reliability / safety counters
# ---------------------------------------------------------------------------


def _count_proposals(env: dict[str, Any]) -> dict[str, Any]:
    """Project the proposal_queue digest into throughput counters.

    Falls back to zeroes when the source is not available, but
    surfaces ``available=False`` so the operator can distinguish
    "no proposals" from "no source".
    """
    if env["state"] != STATE_OK or not env.get("data"):
        return {
            "available": False,
            "proposals_total": 0,
            "by_status": {},
            "by_risk": {},
            "by_type": {},
        }
    data = env["data"]
    counts = data.get("counts") if isinstance(data, dict) else None
    counts = counts if isinstance(counts, dict) else {}
    by_status = counts.get("by_status") or {}
    by_risk = counts.get("by_risk") or {}
    by_type = counts.get("by_type") or {}
    total = counts.get("total")
    if not isinstance(total, int):
        proposals = data.get("proposals") or []
        total = len(proposals) if isinstance(proposals, list) else 0
    return {
        "available": True,
        "proposals_total": int(total),
        "by_status": _coerce_counter(by_status),
        "by_risk": _coerce_counter(by_risk),
        "by_type": _coerce_counter(by_type),
    }


def _count_inbox(env: dict[str, Any]) -> dict[str, Any]:
    if env["state"] != STATE_OK or not env.get("data"):
        return {
            "available": False,
            "inbox_items_total": 0,
            "by_category": {},
            "by_severity": {},
        }
    data = env["data"]
    items = data.get("items") if isinstance(data, dict) else None
    items = items if isinstance(items, list) else []
    by_cat: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category") or "unknown")
        sev = str(it.get("severity") or "unknown")
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_sev[sev] = by_sev.get(sev, 0) + 1
    return {
        "available": True,
        "inbox_items_total": len(items),
        "by_category": _coerce_counter(by_cat),
        "by_severity": _coerce_counter(by_sev),
    }


def _count_pr_lifecycle(env: dict[str, Any]) -> dict[str, Any]:
    if env["state"] != STATE_OK or not env.get("data"):
        return {
            "available": False,
            "prs_seen": 0,
            "merge_allowed": 0,
            "blocked": 0,
            "needs_human": 0,
            "wait_for_rebase": 0,
            "wait_for_checks": 0,
        }
    data = env["data"]
    prs = data.get("prs") if isinstance(data, dict) else None
    prs = prs if isinstance(prs, list) else []
    merge_allowed = 0
    blocked = 0
    needs_human = 0
    rebase = 0
    checks = 0
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        decision = str(pr.get("decision") or "")
        if decision == "merge_allowed":
            merge_allowed += 1
        elif decision.startswith("blocked_"):
            blocked += 1
        elif decision == "needs_human":
            needs_human += 1
        elif decision == "wait_for_rebase":
            rebase += 1
        elif decision == "wait_for_checks":
            checks += 1
    return {
        "available": True,
        "prs_seen": len(prs),
        "merge_allowed": merge_allowed,
        "blocked": blocked,
        "needs_human": needs_human,
        "wait_for_rebase": rebase,
        "wait_for_checks": checks,
    }


def _count_recurring(env: dict[str, Any]) -> dict[str, Any]:
    if env["state"] != STATE_OK or not env.get("data"):
        return {
            "available": False,
            "jobs_total": 0,
            "succeeded": 0,
            "blocked": 0,
            "failed": 0,
            "skipped": 0,
            "timeout": 0,
            "not_run": 0,
            "consecutive_failures_max": 0,
        }
    data = env["data"]
    counts = data.get("counts") if isinstance(data, dict) else {}
    counts = counts if isinstance(counts, dict) else {}
    by_status = counts.get("by_status") if isinstance(counts.get("by_status"), dict) else {}
    total = counts.get("total")
    jobs = data.get("jobs") if isinstance(data, dict) else []
    jobs = jobs if isinstance(jobs, list) else []
    if not isinstance(total, int):
        total = len(jobs)
    cf_max = 0
    for j in jobs:
        if not isinstance(j, dict):
            continue
        cf = j.get("consecutive_failures")
        if isinstance(cf, int) and cf > cf_max:
            cf_max = cf
    return {
        "available": True,
        "jobs_total": int(total),
        "succeeded": int(by_status.get("succeeded", 0) or 0),
        "blocked": int(by_status.get("blocked", 0) or 0),
        "failed": int(by_status.get("failed", 0) or 0),
        "skipped": int(by_status.get("skipped", 0) or 0),
        "timeout": int(by_status.get("timeout", 0) or 0),
        "not_run": int(by_status.get("not_run", 0) or 0),
        "consecutive_failures_max": cf_max,
    }


def _count_runtime(env: dict[str, Any]) -> dict[str, Any]:
    if env["state"] != STATE_OK or not env.get("data"):
        return {
            "available": False,
            "sources_total": 0,
            "ok": 0,
            "degraded": 0,
            "failed": 0,
            "consecutive_failures": 0,
            "last_success_utc": None,
            "last_failure_utc": None,
        }
    data = env["data"]
    counts = data.get("counts") if isinstance(data, dict) else {}
    counts = counts if isinstance(counts, dict) else {}
    by_state = counts.get("by_state") if isinstance(counts.get("by_state"), dict) else {}
    total = counts.get("total")
    sources = data.get("sources") if isinstance(data, dict) else []
    sources = sources if isinstance(sources, list) else []
    if not isinstance(total, int):
        total = len(sources)
    health = data.get("loop_health") if isinstance(data, dict) else {}
    health = health if isinstance(health, dict) else {}
    return {
        "available": True,
        "sources_total": int(total),
        "ok": int(by_state.get("ok", 0) or 0),
        "degraded": int(by_state.get("degraded", 0) or 0)
        + int(by_state.get("not_available", 0) or 0),
        "failed": int(by_state.get("failed", 0) or 0),
        "consecutive_failures": int(health.get("consecutive_failures", 0) or 0),
        "last_success_utc": health.get("last_success_utc"),
        "last_failure_utc": health.get("last_failure_utc"),
    }


def _count_execute_safe(env: dict[str, Any]) -> dict[str, Any]:
    if env["state"] != STATE_OK or not env.get("data"):
        return {
            "available": False,
            "actions_total": 0,
            "by_eligibility": {},
            "by_risk_class": {},
        }
    data = env["data"]
    counts = data.get("counts") if isinstance(data, dict) else {}
    counts = counts if isinstance(counts, dict) else {}
    by_e = counts.get("by_eligibility") if isinstance(counts.get("by_eligibility"), dict) else {}
    by_r = counts.get("by_risk_class") if isinstance(counts.get("by_risk_class"), dict) else {}
    actions = data.get("actions") if isinstance(data, dict) else []
    actions = actions if isinstance(actions, list) else []
    total = counts.get("total")
    if not isinstance(total, int):
        total = len(actions)
    return {
        "available": True,
        "actions_total": int(total),
        "by_eligibility": _coerce_counter(by_e),
        "by_risk_class": _coerce_counter(by_r),
    }


def _coerce_counter(d: Any) -> dict[str, int]:
    """Normalise any dict-shaped object into ``Mapping[str, int]``.
    Non-int values are coerced via ``int()``; failures are dropped.
    Keys are sorted for determinism."""
    if not isinstance(d, Mapping):
        return {}
    out: dict[str, int] = {}
    for k in sorted(str(x) for x in d.keys()):
        v = d.get(k)
        try:
            out[k] = int(v)
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# Operator burden + safety + reliability aggregation
# ---------------------------------------------------------------------------

# Categories that signal a HIGH-risk approval class (all from the
# canonical approval_policy enum).
HIGH_RISK_CATEGORIES: tuple[str, ...] = (
    "high_risk_pr",
    "protected_path_change",
    "frozen_contract_risk",
    "live_paper_shadow_risk_change",
    "ci_or_test_weakening_risk",
    "external_account_or_secret_required",
    "telemetry_or_data_egress_required",
    "paid_tool_required",
    "roadmap_adoption_required",
    "governance_change",
)


def _operator_burden(
    proposals: dict[str, Any],
    inbox: dict[str, Any],
    pr_lc: dict[str, Any],
) -> dict[str, Any]:
    by_status = proposals.get("by_status") or {}
    by_cat = inbox.get("by_category") or {}
    by_sev = inbox.get("by_severity") or {}
    needs_human = int(by_status.get("needs_human", 0) or 0) + int(
        pr_lc.get("needs_human", 0) or 0
    )
    blocked_total = int(by_status.get("blocked", 0) or 0) + int(
        pr_lc.get("blocked", 0) or 0
    )
    approval_required = int(by_cat.get("tooling_requires_approval", 0) or 0)
    manual_route = int(by_cat.get("manual_route_wiring_required", 0) or 0)
    high_risk_blocked = int(by_cat.get("high_risk_pr", 0) or 0)
    unknown_state = int(by_cat.get("unknown_state", 0) or 0)
    estimated_total = (
        needs_human
        + blocked_total
        + approval_required
        + manual_route
        + high_risk_blocked
        + unknown_state
    )
    # Top categories — sorted descending by count, then alphabetical.
    top: list[tuple[str, int]] = []
    for k in sorted(by_cat.keys()):
        v = int(by_cat.get(k, 0) or 0)
        if v > 0:
            top.append((k, v))
    top.sort(key=lambda t: (-t[1], t[0]))
    top_categories = [{"category": c, "count": n} for c, n in top[:5]]
    return {
        "needs_human_total": needs_human,
        "blocked_total": blocked_total,
        "approval_required_total": approval_required,
        "manual_route_wiring_required_total": manual_route,
        "high_risk_blocked_total": high_risk_blocked,
        "unknown_state_total": unknown_state,
        "estimated_operator_actions_total": estimated_total,
        "top_operator_action_categories": top_categories,
        "by_severity": _coerce_counter(by_sev),
    }


def _reliability(
    runtime: dict[str, Any],
    recurring: dict[str, Any],
    src_statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    sources_total = int(runtime.get("sources_total", 0) or 0)
    sources_failed = int(runtime.get("failed", 0) or 0) + int(
        runtime.get("degraded", 0) or 0
    )
    src_failure_rate = (
        round(sources_failed / sources_total, 4) if sources_total > 0 else 0.0
    )
    jobs_total = int(recurring.get("jobs_total", 0) or 0)
    jobs_failed = int(recurring.get("failed", 0) or 0) + int(
        recurring.get("timeout", 0) or 0
    )
    job_failure_rate = (
        round(jobs_failed / jobs_total, 4) if jobs_total > 0 else 0.0
    )
    stale = 0
    malformed = 0
    missing = 0
    for s in src_statuses:
        st = s.get("state")
        if st == STATE_MALFORMED or st == STATE_NOT_AN_OBJECT:
            malformed += 1
        elif st == STATE_MISSING:
            missing += 1
        elif st == STATE_UNREADABLE:
            stale += 1
        elif st == STATE_OK and bool(s.get("is_stale", False)):
            # v3.15.15.27 — an ok-parsing artifact whose
            # generated_at_utc is older than the staleness threshold
            # is still counted as a reliability concern.
            stale += 1
    return {
        "runtime_consecutive_failures": int(runtime.get("consecutive_failures", 0) or 0),
        "recurring_consecutive_failures_max": int(
            recurring.get("consecutive_failures_max", 0) or 0
        ),
        "source_failure_rate": src_failure_rate,
        "job_failure_rate": job_failure_rate,
        "stale_artifact_count": stale,
        "malformed_artifact_count": malformed,
        "missing_artifact_count": missing,
        "last_success_at_utc": runtime.get("last_success_utc"),
        "last_failure_at_utc": runtime.get("last_failure_utc"),
    }


def _safety(
    inbox: dict[str, Any],
    execute_safe: dict[str, Any],
    proposals: dict[str, Any],
) -> dict[str, Any]:
    by_cat = inbox.get("by_category") or {}
    by_eligibility = execute_safe.get("by_eligibility") or {}
    by_risk = execute_safe.get("by_risk_class") or {}
    proposal_by_risk = proposals.get("by_risk") or {}

    # The safety contract: nothing classified HIGH or UNKNOWN may be
    # ELIGIBLE (executable) at the same time. We approximate this as
    # "count of HIGH+UNKNOWN actions that are also eligible".
    # ``execute_safe_controls`` does not currently emit cross-tabulated
    # data, so we read the action list directly when available.
    high_or_unknown_executable = 0
    actions = execute_safe.get("_actions_passthrough") or []
    if isinstance(actions, list):
        for a in actions:
            if not isinstance(a, dict):
                continue
            r = str(a.get("risk_class", "")).upper()
            e = str(a.get("eligibility", "")).lower()
            if r in ("HIGH", "UNKNOWN") and e == "eligible":
                high_or_unknown_executable += 1

    return {
        "high_or_unknown_executable_count": high_or_unknown_executable,
        "frozen_contract_risk_count": int(by_cat.get("frozen_contract_risk", 0) or 0),
        "protected_path_risk_count": int(by_cat.get("protected_path_change", 0) or 0),
        "live_paper_shadow_risk_count": int(
            by_cat.get("live_paper_shadow_risk_change", 0) or 0
        ),
        "ci_or_test_weakening_risk_count": int(
            by_cat.get("ci_or_test_weakening_risk", 0) or 0
        ),
        "secret_or_external_account_required_count": int(
            by_cat.get("external_account_or_secret_required", 0) or 0
        ),
        "telemetry_or_data_egress_count": int(
            by_cat.get("telemetry_or_data_egress_required", 0) or 0
        ),
        "paid_tool_required_count": int(by_cat.get("paid_tool_required", 0) or 0),
        "high_risk_proposal_count": int(proposal_by_risk.get("HIGH", 0) or 0),
        "unknown_risk_proposal_count": int(proposal_by_risk.get("UNKNOWN", 0) or 0),
        "execute_safe_eligible_count": int(by_eligibility.get("eligible", 0) or 0),
        "execute_safe_blocked_count": int(by_eligibility.get("blocked", 0) or 0),
        "execute_safe_high_count": int(by_risk.get("HIGH", 0) or 0),
        "policy_version": _approval_policy.MODULE_VERSION,
        "summary": (
            "ok"
            if high_or_unknown_executable == 0
            else "unsafe_state_detected"
        ),
    }


# ---------------------------------------------------------------------------
# Trend windows from history.jsonl files
# ---------------------------------------------------------------------------


def _parse_iso(s: Any) -> _dt.datetime | None:
    if not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        return _dt.datetime.fromisoformat(s2)
    except (TypeError, ValueError):
        return None


def _window_filter(
    rows: list[dict[str, Any]],
    *,
    now: _dt.datetime,
    seconds: int | None,
) -> list[dict[str, Any]]:
    if seconds is None:
        return rows
    cutoff = now - _dt.timedelta(seconds=seconds)
    out: list[dict[str, Any]] = []
    for r in rows:
        ts = _parse_iso(r.get("generated_at_utc"))
        if ts is None:
            continue
        if ts >= cutoff:
            out.append(r)
    return out


def _trend_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate a list of historical digest rows into a few simple
    bounded counters. Designed for both runtime and recurring
    histories — they share enough shape (counts.total etc.) that a
    single aggregator works."""
    if not rows:
        return {"status": "not_available", "reason": "no_history"}
    n = len(rows)
    total_runs = n
    failed_runs = 0
    succeeded_runs = 0
    degraded_runs = 0
    consecutive_failures_max = 0
    for r in rows:
        rec = str(r.get("final_recommendation") or "")
        cf = 0
        health = r.get("loop_health")
        if isinstance(health, dict):
            cf = int(health.get("consecutive_failures", 0) or 0)
        consecutive_failures_max = max(consecutive_failures_max, cf)
        if rec.startswith("runtime_halt") or "consecutive_failures" in rec:
            failed_runs += 1
        elif rec in ("all_sources_ok", "all_jobs_ok", "healthy", "ok"):
            succeeded_runs += 1
        elif rec.startswith("degraded"):
            degraded_runs += 1
    return {
        "status": "ok",
        "total_runs": total_runs,
        "succeeded_runs": succeeded_runs,
        "failed_runs": failed_runs,
        "degraded_runs": degraded_runs,
        "consecutive_failures_max": consecutive_failures_max,
    }


def _trends(
    runtime_history: list[dict[str, Any]],
    recurring_history: list[dict[str, Any]],
    *,
    now: _dt.datetime,
) -> dict[str, Any]:
    return {
        "current": {
            "runtime": _trend_aggregate(runtime_history[-1:]),
            "recurring": _trend_aggregate(recurring_history[-1:]),
        },
        TREND_LAST_24H: {
            "runtime": _trend_aggregate(
                _window_filter(runtime_history, now=now, seconds=24 * 3600)
            ),
            "recurring": _trend_aggregate(
                _window_filter(recurring_history, now=now, seconds=24 * 3600)
            ),
        },
        TREND_LAST_7D: {
            "runtime": _trend_aggregate(
                _window_filter(runtime_history, now=now, seconds=7 * 24 * 3600)
            ),
            "recurring": _trend_aggregate(
                _window_filter(recurring_history, now=now, seconds=7 * 24 * 3600)
            ),
        },
        TREND_ALL_TIME: {
            "runtime": _trend_aggregate(runtime_history),
            "recurring": _trend_aggregate(recurring_history),
        },
    }


# ---------------------------------------------------------------------------
# Final recommendation logic
# ---------------------------------------------------------------------------


def _final_recommendation(
    *,
    src_statuses: list[dict[str, Any]],
    operator_burden: dict[str, Any],
    reliability: dict[str, Any],
    safety: dict[str, Any],
) -> str:
    if safety.get("high_or_unknown_executable_count", 0) > 0:
        return REC_UNSAFE
    missing = sum(
        1 for s in src_statuses if s.get("state") in (STATE_MISSING, STATE_NOT_AN_OBJECT)
    )
    if missing == len(src_statuses):
        return REC_NOT_AVAILABLE
    if reliability.get("missing_artifact_count", 0) >= 2:
        return REC_DEGRADED_MISSING
    if reliability.get("malformed_artifact_count", 0) > 0:
        return REC_DEGRADED_FAILURES
    if reliability.get("runtime_consecutive_failures", 0) >= 3:
        return REC_DEGRADED_FAILURES
    if operator_burden.get("estimated_operator_actions_total", 0) > 0:
        return REC_ACTION_REQUIRED
    return REC_HEALTHY


# ---------------------------------------------------------------------------
# collect_snapshot / write_outputs
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    stale_threshold_seconds: int | None = None,
) -> dict[str, Any]:
    """Build the full metrics digest. Pure with respect to the
    filesystem state at call time. ``frozen_utc`` pins the
    generated_at_utc field for deterministic tests.
    ``stale_threshold_seconds`` overrides the default
    ``STALE_THRESHOLD_SECONDS_DEFAULT``; pass an explicit value in
    tests to make staleness deterministic without depending on the
    real clock relative to the artifact mtime."""
    src_envelopes: dict[str, dict[str, Any]] = {
        "workloop_runtime": _read_json_artifact(SOURCE_WORKLOOP_RUNTIME),
        "recurring_maintenance": _read_json_artifact(SOURCE_RECURRING_MAINTENANCE),
        "proposal_queue": _read_json_artifact(SOURCE_PROPOSAL_QUEUE),
        "approval_inbox": _read_json_artifact(SOURCE_APPROVAL_INBOX),
        "github_pr_lifecycle": _read_json_artifact(SOURCE_PR_LIFECYCLE),
        "execute_safe_controls": _read_json_artifact(SOURCE_EXECUTE_SAFE_CONTROLS),
    }

    threshold = (
        stale_threshold_seconds
        if stale_threshold_seconds is not None
        else _stale_threshold_from_env()
    )
    # Anchor "now" to the pinned frozen_utc when provided so stale
    # detection is deterministic for a given input set.
    now_dt = _parse_iso(frozen_utc) if frozen_utc else _utcnow_dt()
    if now_dt is None:
        now_dt = _utcnow_dt()

    src_statuses: list[dict[str, Any]] = []
    for name, rel in SOURCE_ORDER:
        env = src_envelopes[name]
        row: dict[str, Any] = {
            "source": name,
            "artifact_path": rel,
            "state": env["state"],
            "reason": env["reason"],
        }
        # v3.15.15.27 — annotate ok rows with age + staleness so
        # the operator can distinguish "fresh" from "ancient" at
        # a glance. Inputs without a generated_at_utc field are
        # left without an age (no false certainty).
        if env["state"] == STATE_OK and isinstance(env.get("data"), dict):
            gen = env["data"].get("generated_at_utc")
            gen_dt = _parse_iso(gen) if isinstance(gen, str) else None
            if gen_dt is not None:
                age_seconds = max(0, int((now_dt - gen_dt).total_seconds()))
                row["age_seconds"] = age_seconds
                row["is_stale"] = age_seconds > threshold
            else:
                row["age_seconds"] = None
                row["is_stale"] = False
        src_statuses.append(row)

    proposals = _count_proposals(src_envelopes["proposal_queue"])
    inbox = _count_inbox(src_envelopes["approval_inbox"])
    pr_lc = _count_pr_lifecycle(src_envelopes["github_pr_lifecycle"])
    runtime = _count_runtime(src_envelopes["workloop_runtime"])
    recurring = _count_recurring(src_envelopes["recurring_maintenance"])
    execute_safe = _count_execute_safe(src_envelopes["execute_safe_controls"])

    # Cross-tab pass-through for safety eval — read raw actions.
    es_data = src_envelopes["execute_safe_controls"].get("data") or {}
    if isinstance(es_data, dict):
        execute_safe["_actions_passthrough"] = es_data.get("actions") or []
    else:
        execute_safe["_actions_passthrough"] = []

    operator_burden = _operator_burden(proposals, inbox, pr_lc)
    reliability = _reliability(runtime, recurring, src_statuses)
    safety = _safety(inbox, execute_safe, proposals)

    runtime_history = _read_jsonl_history(SOURCE_WORKLOOP_RUNTIME_HISTORY)
    recurring_history = _read_jsonl_history(SOURCE_RECURRING_MAINTENANCE_HISTORY)
    trends = _trends(runtime_history, recurring_history, now=_utcnow_dt())

    final_rec = _final_recommendation(
        src_statuses=src_statuses,
        operator_burden=operator_burden,
        reliability=reliability,
        safety=safety,
    )

    # Strip the internal pass-through field — it is not part of the
    # public schema.
    execute_safe.pop("_actions_passthrough", None)

    snap: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "autonomy_metrics_digest",
        "module_version": MODULE_VERSION,
        "metrics_version": METRICS_VERSION,
        "generated_at_utc": frozen_utc or _utcnow(),
        "source_statuses": src_statuses,
        "throughput": {
            "proposals_total": proposals.get("proposals_total", 0),
            "proposals_by_status": proposals.get("by_status", {}),
            "proposals_by_risk": proposals.get("by_risk", {}),
            "proposals_by_type": proposals.get("by_type", {}),
            "inbox_items_total": inbox.get("inbox_items_total", 0),
            "inbox_items_by_category": inbox.get("by_category", {}),
            "inbox_items_by_severity": inbox.get("by_severity", {}),
            "pr_lifecycle_prs_seen": pr_lc.get("prs_seen", 0),
            "pr_lifecycle_merge_allowed": pr_lc.get("merge_allowed", 0),
            "pr_lifecycle_blocked": pr_lc.get("blocked", 0),
            "pr_lifecycle_needs_human": pr_lc.get("needs_human", 0),
            "pr_lifecycle_wait_for_rebase": pr_lc.get("wait_for_rebase", 0),
            "pr_lifecycle_wait_for_checks": pr_lc.get("wait_for_checks", 0),
            "recurring_jobs_total": recurring.get("jobs_total", 0),
            "recurring_jobs_succeeded": recurring.get("succeeded", 0),
            "recurring_jobs_blocked": recurring.get("blocked", 0),
            "recurring_jobs_failed": recurring.get("failed", 0),
            "recurring_jobs_skipped": recurring.get("skipped", 0),
            "recurring_jobs_timeout": recurring.get("timeout", 0),
            "recurring_jobs_not_run": recurring.get("not_run", 0),
            "runtime_sources_total": runtime.get("sources_total", 0),
            "runtime_sources_ok": runtime.get("ok", 0),
            "runtime_sources_degraded": runtime.get("degraded", 0),
            "runtime_sources_failed": runtime.get("failed", 0),
            "execute_safe_actions_total": execute_safe.get("actions_total", 0),
            "execute_safe_by_eligibility": execute_safe.get("by_eligibility", {}),
            "execute_safe_by_risk_class": execute_safe.get("by_risk_class", {}),
        },
        "operator_burden": operator_burden,
        "reliability": reliability,
        "safety": safety,
        "trends": trends,
        "policy": {
            "module_version": _approval_policy.MODULE_VERSION,
            "schema_version": _approval_policy.SCHEMA_VERSION,
            "high_or_unknown_is_executable": False,
        },
        "final_recommendation": final_rec,
        "safe_to_execute": False,
    }

    _approval_policy.assert_no_credential_values(snap)
    return snap


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    """Atomic write of latest.json + timestamped copy + history append."""
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = snapshot["generated_at_utc"].replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    history = DIGEST_DIR_JSON / "history.jsonl"
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot() -> dict[str, Any] | None:
    """Helper for downstream consumers (status surface). Returns the
    parsed digest or ``None`` if the artifact is missing/malformed."""
    env = _read_json_artifact(DIGEST_DIR_JSON / "latest.json")
    if env["state"] == STATE_OK:
        return env["data"]
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.autonomy_metrics",
        description=(
            "Read-only autonomy throughput / observability metrics "
            "(v3.15.15.25). Stdlib-only."
        ),
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--collect", action="store_true", help="Collect and write a snapshot.")
    g.add_argument("--status", action="store_true", help="Read and print the latest snapshot.")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="With --collect, skip the artifact write (useful for CI).",
    )
    parser.add_argument(
        "--frozen-utc",
        type=str,
        default=None,
        help="Pin generated_at_utc for deterministic tests.",
    )
    parser.add_argument(
        "--stale-threshold-seconds",
        type=int,
        default=None,
        help=(
            "Override the staleness threshold (default: "
            f"{STALE_THRESHOLD_SECONDS_DEFAULT}s = 24h). "
            "Sources whose generated_at_utc is older than this "
            "are counted under reliability.stale_artifact_count."
        ),
    )
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            print(json.dumps({"status": "not_available", "reason": "missing"}, indent=2))
            return 1
        print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    if args.collect:
        snap = collect_snapshot(
            frozen_utc=args.frozen_utc,
            stale_threshold_seconds=args.stale_threshold_seconds,
        )
        if not args.no_write:
            paths = write_outputs(snap)
            print(json.dumps({"status": "ok", "paths": paths}, indent=2))
        else:
            print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    parser.error("no mode chosen")
    return 2  # unreachable


if __name__ == "__main__":
    sys.exit(main())
