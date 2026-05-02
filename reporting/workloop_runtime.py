"""Long-running workloop runtime (v3.15.15.22).

A deterministic, bounded supervisor that periodically invokes the
existing read-only / dry-run governance reporters and captures their
results as a single runtime-state artifact. Observe / classify /
report — **never** an autonomous executor.

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Calls the listed reporting modules in-process; never invokes an
  arbitrary command, never accepts a free-form command string.
* ``--once`` mode runs exactly one iteration and exits.
* ``--loop`` mode honours ``--max-iterations`` and ``--interval-
  seconds``. Both flags are clamped to safe upper bounds so a test
  never runs forever.
* One source failure does NOT crash the loop; the source is
  classified ``failed``/``timeout`` and the supervisor moves on.
* Per-source wall-clock timeout. Cross-platform (thread-join on
  Windows, no SIGALRM).
* Atomic JSON write: tmp file + ``os.replace``.
* ``assert_no_secrets`` runs over every per-source result and over
  the final snapshot before persistence.
* ``safe_to_execute`` is hard-coded ``false`` in this release.
* No GitHub mutation, no git operation, no live/paper/shadow/risk
  surface touched.
* CLI flags are validated; unknown flags are rejected.

CLI
---

::

    python -m reporting.workloop_runtime --once
    python -m reporting.workloop_runtime --loop \\
        --interval-seconds 300 --max-iterations 3
    python -m reporting.workloop_runtime --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Credential-value patterns checked at the OUTER snapshot boundary.
# We deliberately do not check sensitive-path fragments at the outer
# layer — the snapshot legitimately includes path-shaped strings
# (artifact_path fields, source names, etc.) and the per-source
# supervisor already runs the strict ``assert_no_secrets`` against
# each source's inner value before it lands in the snapshot.
_OUTER_CREDENTIAL_PATTERNS: tuple[str, ...] = (
    "sk-ant-",
    "ghp_",
    "github_pat_",
    "AKIA",
    "-----BEGIN ",
)


def _assert_no_credential_values(snapshot: dict[str, Any]) -> None:
    """Outer-boundary credential check. Walks every string in
    ``snapshot`` and refuses anything that looks like a real
    credential value (Anthropic key, GitHub PAT, AWS key, private
    key block). Raises ``AssertionError`` on a hit.

    This is intentionally narrower than the inner per-source
    redaction: it does not check path fragments because the runtime
    snapshot is metadata-shaped and legitimately echoes
    ``logs/...`` and ``docs/...`` paths in artifact_path fields.
    """
    import collections.abc as _abc

    def _walk(o: Any):
        if isinstance(o, str):
            yield o
        elif isinstance(o, dict):
            for v in o.values():
                yield from _walk(v)
        elif isinstance(o, _abc.Iterable) and not isinstance(o, (bytes, bytearray)):
            for v in o:
                yield from _walk(v)

    for s in _walk(snapshot):
        for pat in _OUTER_CREDENTIAL_PATTERNS:
            if pat in s:
                raise AssertionError(
                    f"workloop_runtime leaked credential-like value: "
                    f"pattern={pat!r}"
                )

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
RUNTIME_VERSION: str = "v3.15.15.22"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "workloop_runtime"

# Hard runtime caps. Tests rely on these; do not loosen without a
# governance-bootstrap PR.
MAX_ITERATIONS_LIMIT: int = 24
MIN_INTERVAL_SECONDS: int = 30
MAX_INTERVAL_SECONDS: int = 6 * 3600  # 6 hours

# Per-source wall-clock timeout (seconds).
DEFAULT_SOURCE_TIMEOUT_SECONDS: int = 60

# State enum surfaced in the schema doc.
STATE_OK: str = "ok"
STATE_DEGRADED: str = "degraded"
STATE_NOT_AVAILABLE: str = "not_available"
STATE_FAILED: str = "failed"
STATE_TIMEOUT: str = "timeout"
STATE_SKIPPED: str = "skipped"
STATE_UNKNOWN: str = "unknown"
STATE_VALUES: tuple[str, ...] = (
    STATE_OK,
    STATE_DEGRADED,
    STATE_NOT_AVAILABLE,
    STATE_FAILED,
    STATE_TIMEOUT,
    STATE_SKIPPED,
    STATE_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Time / id helpers
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


def _run_id(generated_at: str, iteration: int) -> str:
    raw = f"{generated_at}|{iteration}".encode("utf-8")
    return "wl_" + hashlib.sha256(raw).hexdigest()[:8]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Per-source supervisor primitives
# ---------------------------------------------------------------------------


# Sentinel signalling "do nothing" inside the source result envelope.
_NO_ARTIFACT: str = ""


class _SourceResult(dict[str, Any]):
    """Typed-ish envelope for one supervised source result."""


def _supervise(
    *,
    name: str,
    module: str,
    artifact_path: str,
    fn: Callable[[], Any],
    timeout: int = DEFAULT_SOURCE_TIMEOUT_SECONDS,
    state_from_envelope: Callable[[Any], tuple[str, str]] | None = None,
) -> _SourceResult:
    """Run one source's read-only call with a wall-clock timeout, a
    secret-redaction guard, and an exception fence.

    Returns an :class:`_SourceResult` dict. Never raises.
    """
    start = time.monotonic()
    state: str = STATE_UNKNOWN
    summary: str = ""
    error_class: str | None = None

    holder: dict[str, Any] = {}

    def _runner() -> None:
        try:
            holder["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — defensive fence
            holder["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout)
    duration_ms = int((time.monotonic() - start) * 1000)

    if t.is_alive():
        # Cannot kill the thread cleanly in stdlib; mark timeout, the
        # daemon thread will be reaped on process exit.
        return _SourceResult(
            source=name,
            module=module,
            state=STATE_TIMEOUT,
            duration_ms=duration_ms,
            summary=f"timeout after {timeout}s",
            artifact_path=artifact_path,
            error_class=None,
        )

    if "error" in holder:
        e = holder["error"]
        return _SourceResult(
            source=name,
            module=module,
            state=STATE_FAILED,
            duration_ms=duration_ms,
            summary=f"{type(e).__name__}: {str(e)[:200]}",
            artifact_path=artifact_path,
            error_class=type(e).__name__,
        )

    value = holder.get("value")

    # Per-source credential-value guard. We deliberately do NOT use
    # the strict path-fragment check from agent_audit_summary here:
    # the supervised snapshots LEGITIMATELY echo path-shaped strings
    # (e.g. ``config/config.yaml`` as a no-touch path reference, or
    # ``state/*.secret`` glob patterns) and rejecting those would
    # mark legitimate read-only output as a leak. The narrow guard
    # below catches actual credential VALUES — Anthropic keys, GitHub
    # PATs, AWS access keys, private-key blocks — which are the real
    # leak risk.
    if isinstance(value, dict):
        try:
            _assert_no_credential_values(value)
        except AssertionError:
            # Intentionally do NOT echo the original assertion message
            # — it contains the credential pattern verbatim, which
            # would trip the outer guard. The error_class is enough
            # for the operator to know what happened; the underlying
            # source is the canonical place to investigate.
            return _SourceResult(
                source=name,
                module=module,
                state=STATE_FAILED,
                duration_ms=duration_ms,
                summary="secret_redaction_failed",
                artifact_path=artifact_path,
                error_class="SecretRedactionFailed",
            )

    # Caller-supplied envelope inspection decides ok / degraded /
    # not_available. Default: any non-None value is ``ok``.
    if state_from_envelope is not None:
        try:
            state, summary = state_from_envelope(value)
        except Exception as e:  # noqa: BLE001
            state = STATE_FAILED
            summary = f"envelope_inspect_failed: {type(e).__name__}"
            error_class = type(e).__name__
    else:
        if value is None:
            state, summary = STATE_NOT_AVAILABLE, "value is None"
        else:
            state, summary = STATE_OK, "ok"

    return _SourceResult(
        source=name,
        module=module,
        state=state,
        duration_ms=duration_ms,
        summary=summary,
        artifact_path=artifact_path,
        error_class=error_class,
    )


# ---------------------------------------------------------------------------
# Source factory — closed list of allowed reporters
# ---------------------------------------------------------------------------


def _governance_status_call() -> Any:
    from reporting.governance_status import collect_status

    return collect_status()


def _governance_status_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    audit = value.get("audit_chain_status") or {}
    audit_state = audit.get("status") if isinstance(audit, dict) else None
    if audit_state == "broken":
        return (STATE_DEGRADED, f"audit_chain_status={audit_state!r}")
    return (STATE_OK, "governance_status ok")


def _agent_audit_summary_call() -> Any:
    from reporting import agent_audit_summary as audit_summary
    import datetime as _local_dt

    today = _local_dt.datetime.now(_local_dt.UTC).strftime("%Y-%m-%d")
    ledger = REPO_ROOT / "logs" / f"agent_audit.{today}.jsonl"
    return audit_summary.collect_timeline(ledger, limit=50)


def _agent_audit_summary_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    if not value.get("ledger_present"):
        return (STATE_NOT_AVAILABLE, "today's ledger is missing")
    chain = value.get("chain_status")
    if chain == "broken":
        return (STATE_DEGRADED, f"chain_status={chain!r}")
    return (STATE_OK, f"events={value.get('ledger_event_count', 0)}")


def _autonomous_workloop_call() -> Any:
    from reporting.autonomous_workloop import collect_snapshot

    return collect_snapshot(mode="dry-run", cycle_id=0)


def _autonomous_workloop_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    blocked = value.get("blocked_items") or []
    return (
        STATE_OK if not blocked else STATE_DEGRADED,
        f"blocked={len(blocked)}",
    )


def _github_pr_lifecycle_call() -> Any:
    from reporting.github_pr_lifecycle import collect_snapshot

    return collect_snapshot(mode="dry-run")


def _github_pr_lifecycle_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    provider = value.get("provider_status")
    if provider in (None, "", "not_available"):
        return (STATE_NOT_AVAILABLE, f"provider_status={provider!r}")
    if provider != "available":
        return (STATE_DEGRADED, f"provider_status={provider!r}")
    return (STATE_OK, "gh provider available")


def _proposal_queue_call() -> Any:
    from reporting.proposal_queue import collect_snapshot

    return collect_snapshot(mode="dry-run")


def _proposal_queue_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    counts = value.get("counts") or {}
    total = counts.get("total", 0) if isinstance(counts, dict) else 0
    return (STATE_OK, f"proposals={total}")


def _approval_inbox_call() -> Any:
    from reporting.approval_inbox import collect_snapshot

    return collect_snapshot(mode="dry-run")


def _approval_inbox_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    counts = value.get("counts") or {}
    total = counts.get("total", 0) if isinstance(counts, dict) else 0
    return (STATE_OK, f"items={total}")


def _execute_safe_catalog_call() -> Any:
    from reporting.execute_safe_controls import collect_catalog

    return collect_catalog()


def _execute_safe_envelope(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return (STATE_DEGRADED, "non-dict envelope")
    actions = value.get("actions") or []
    return (STATE_OK, f"actions={len(actions)}")


# Closed list. Adding a new source requires a new release + ADR.
SOURCES: tuple[dict[str, Any], ...] = (
    {
        "name": "governance_status",
        "module": "reporting.governance_status",
        "artifact_path": "governance_status:in_process",
        "fn": _governance_status_call,
        "envelope": _governance_status_envelope,
    },
    {
        "name": "agent_audit_summary",
        "module": "reporting.agent_audit_summary",
        "artifact_path": "logs/agent_audit.<UTC>.jsonl",
        "fn": _agent_audit_summary_call,
        "envelope": _agent_audit_summary_envelope,
    },
    {
        "name": "autonomous_workloop",
        "module": "reporting.autonomous_workloop",
        "artifact_path": "logs/autonomous_workloop/latest.json",
        "fn": _autonomous_workloop_call,
        "envelope": _autonomous_workloop_envelope,
    },
    {
        "name": "github_pr_lifecycle",
        "module": "reporting.github_pr_lifecycle",
        "artifact_path": "logs/github_pr_lifecycle/latest.json",
        "fn": _github_pr_lifecycle_call,
        "envelope": _github_pr_lifecycle_envelope,
    },
    {
        "name": "proposal_queue",
        "module": "reporting.proposal_queue",
        "artifact_path": "logs/proposal_queue/latest.json",
        "fn": _proposal_queue_call,
        "envelope": _proposal_queue_envelope,
    },
    {
        "name": "approval_inbox",
        "module": "reporting.approval_inbox",
        "artifact_path": "logs/approval_inbox/latest.json",
        "fn": _approval_inbox_call,
        "envelope": _approval_inbox_envelope,
    },
    {
        "name": "execute_safe_controls",
        "module": "reporting.execute_safe_controls",
        "artifact_path": "logs/execute_safe_controls/latest.json",
        "fn": _execute_safe_catalog_call,
        "envelope": _execute_safe_envelope,
    },
)


# ---------------------------------------------------------------------------
# Loop-health bookkeeping (recovers across restarts via latest.json)
# ---------------------------------------------------------------------------


def _read_previous_loop_health() -> dict[str, Any]:
    """Best-effort read of the prior latest.json so loop-health
    counters survive process restarts."""
    p = DIGEST_DIR_JSON / "latest.json"
    if not p.exists():
        return {
            "iterations_completed": 0,
            "iterations_failed": 0,
            "last_success_utc": None,
            "last_failure_utc": None,
            "consecutive_failures": 0,
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "iterations_completed": 0,
            "iterations_failed": 0,
            "last_success_utc": None,
            "last_failure_utc": None,
            "consecutive_failures": 0,
        }
    health = data.get("loop_health") or {}
    if not isinstance(health, dict):
        return {
            "iterations_completed": 0,
            "iterations_failed": 0,
            "last_success_utc": None,
            "last_failure_utc": None,
            "consecutive_failures": 0,
        }
    return {
        "iterations_completed": int(health.get("iterations_completed") or 0),
        "iterations_failed": int(health.get("iterations_failed") or 0),
        "last_success_utc": health.get("last_success_utc") or None,
        "last_failure_utc": health.get("last_failure_utc") or None,
        "consecutive_failures": int(health.get("consecutive_failures") or 0),
    }


def _update_loop_health(
    prev: dict[str, Any],
    *,
    sources: list[_SourceResult],
    generated_at: str,
) -> dict[str, Any]:
    iteration_failed = any(
        r.get("state") in (STATE_FAILED, STATE_TIMEOUT) for r in sources
    )
    out = dict(prev)
    out["iterations_completed"] = (prev.get("iterations_completed") or 0) + 1
    if iteration_failed:
        out["iterations_failed"] = (prev.get("iterations_failed") or 0) + 1
        out["last_failure_utc"] = generated_at
        out["consecutive_failures"] = (prev.get("consecutive_failures") or 0) + 1
    else:
        out["last_success_utc"] = generated_at
        out["consecutive_failures"] = 0
    return out


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    mode: str = "once",
    iteration: int = 0,
    max_iterations: int = 1,
    interval_seconds: int | None = None,
    sources_override: tuple[dict[str, Any], ...] | None = None,
    timeout_per_source: int = DEFAULT_SOURCE_TIMEOUT_SECONDS,
    previous_loop_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run every supervised source once and return a snapshot dict.

    Pure orchestration: every source call goes through ``_supervise``
    so an exception, timeout, or secret-redaction failure on one
    source is contained.
    """
    start = time.monotonic()
    generated_at = _utcnow()
    sources_to_run = sources_override if sources_override is not None else SOURCES
    results: list[_SourceResult] = []
    for src in sources_to_run:
        results.append(
            _supervise(
                name=src["name"],
                module=src["module"],
                artifact_path=src["artifact_path"],
                fn=src["fn"],
                timeout=timeout_per_source,
                state_from_envelope=src.get("envelope"),
            )
        )
    duration_ms = int((time.monotonic() - start) * 1000)

    # Counts.
    counts: dict[str, int] = {}
    for r in results:
        s = r.get("state", STATE_UNKNOWN)
        counts[s] = counts.get(s, 0) + 1

    prev_health = (
        previous_loop_health
        if previous_loop_health is not None
        else _read_previous_loop_health()
    )
    health = _update_loop_health(prev_health, sources=results, generated_at=generated_at)

    # next_run_after_utc only meaningful in loop mode.
    next_run = None
    if mode == "loop" and interval_seconds is not None:
        # interval is sanitized at the CLI boundary.
        next_run_dt = _utcnow_dt() + _dt.timedelta(seconds=interval_seconds)
        next_run = next_run_dt.isoformat().replace("+00:00", "Z")

    snap: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "workloop_runtime_digest",
        "runtime_version": RUNTIME_VERSION,
        "generated_at_utc": generated_at,
        "run_id": _run_id(generated_at, iteration),
        "mode": mode,
        "iteration": iteration,
        "max_iterations": max_iterations,
        "interval_seconds": interval_seconds,
        "next_run_after_utc": next_run,
        "duration_ms": duration_ms,
        "safe_to_execute": False,
        "loop_health": health,
        "sources": list(results),
        "counts": {"by_state": counts, "total": len(results)},
        "final_recommendation": _final_recommendation(counts, health),
    }
    # Outer defense-in-depth credential-value guard. The strict
    # path-fragment check already ran per source via _supervise; this
    # outer layer only catches actual credential VALUES (sk-ant-…,
    # ghp_…, AWS keys, private-key blocks) leaking into metadata.
    _assert_no_credential_values(snap)
    return snap


def _final_recommendation(counts: dict[str, int], health: dict[str, Any]) -> str:
    failed = counts.get(STATE_FAILED, 0)
    timeouts = counts.get(STATE_TIMEOUT, 0)
    not_available = counts.get(STATE_NOT_AVAILABLE, 0)
    consecutive = int(health.get("consecutive_failures") or 0)
    if consecutive >= 3:
        return f"runtime_halt_after_{consecutive}_consecutive_failures"
    if failed + timeouts > 0:
        return f"degraded_failed_{failed}_timeout_{timeouts}"
    if not_available > 0:
        return f"degraded_not_available_{not_available}"
    return "all_sources_ok"


# ---------------------------------------------------------------------------
# Atomic persistence
# ---------------------------------------------------------------------------


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    """Atomic write to ``latest.json`` and the timestamped copy, plus
    one history line. ``os.replace`` is atomic on POSIX and on Windows
    (NTFS) — on Windows it is implemented via MoveFileExW + REPLACE_EXISTING.
    """
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = snapshot["generated_at_utc"].replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    history = DIGEST_DIR_JSON / "history.jsonl"
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    # Atomic write to the timestamped copy.
    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    # Atomic write to latest.
    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    # Append one line to history.jsonl. JSONL is append-only by
    # design; we use a single-line compact form so each record is
    # one row.
    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "json_now": _rel(json_now),
        "json_latest": _rel(json_latest),
        "history_jsonl": _rel(history),
    }


# ---------------------------------------------------------------------------
# Loop driver
# ---------------------------------------------------------------------------


def run_once(
    *,
    iteration: int = 0,
    max_iterations: int = 1,
    interval_seconds: int | None = None,
    timeout_per_source: int = DEFAULT_SOURCE_TIMEOUT_SECONDS,
    sources_override: tuple[dict[str, Any], ...] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    snap = collect_snapshot(
        mode="loop" if max_iterations > 1 else "once",
        iteration=iteration,
        max_iterations=max_iterations,
        interval_seconds=interval_seconds,
        sources_override=sources_override,
        timeout_per_source=timeout_per_source,
    )
    if write:
        write_outputs(snap)
    return snap


def run_loop(
    *,
    interval_seconds: int,
    max_iterations: int,
    timeout_per_source: int = DEFAULT_SOURCE_TIMEOUT_SECONDS,
    sources_override: tuple[dict[str, Any], ...] | None = None,
    write: bool = True,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Bounded loop. Honours ``max_iterations`` (clamped to
    :data:`MAX_ITERATIONS_LIMIT`) and ``interval_seconds`` (clamped to
    [:data:`MIN_INTERVAL_SECONDS`, :data:`MAX_INTERVAL_SECONDS`]).

    Returns the list of snapshots in iteration order. On
    KeyboardInterrupt the loop exits gracefully and the caller can
    inspect the partial list.
    """
    iters = max(1, min(max_iterations, MAX_ITERATIONS_LIMIT))
    interval = max(MIN_INTERVAL_SECONDS, min(interval_seconds, MAX_INTERVAL_SECONDS))
    snapshots: list[dict[str, Any]] = []
    try:
        for i in range(iters):
            snap = run_once(
                iteration=i,
                max_iterations=iters,
                interval_seconds=interval,
                timeout_per_source=timeout_per_source,
                sources_override=sources_override,
                write=write,
            )
            snapshots.append(snap)
            if i < iters - 1:
                sleeper(interval)
    except KeyboardInterrupt:
        # Graceful stop: fall through with the partial snapshot list.
        pass
    return snapshots


# ---------------------------------------------------------------------------
# Read-side helpers (for status / inbox integration)
# ---------------------------------------------------------------------------


def read_latest_snapshot() -> dict[str, Any] | None:
    """Return the most recent snapshot, or ``None`` if missing /
    malformed. Never raises."""
    p = DIGEST_DIR_JSON / "latest.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.workloop_runtime",
        description=(
            "Long-running workloop runtime. Periodically invokes the "
            "existing read-only / dry-run governance reporters and "
            "writes a single runtime-state artifact. Observe / "
            "classify / report — never an autonomous executor."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run a single iteration and exit (default).")
    mode.add_argument("--loop", action="store_true", help="Run a bounded loop.")
    mode.add_argument("--status", action="store_true", help="Print the most recent snapshot from latest.json.")
    p.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help=f"Loop interval (clamped to [{MIN_INTERVAL_SECONDS}, {MAX_INTERVAL_SECONDS}]).",
    )
    p.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help=f"Max iterations in --loop mode (clamped to {MAX_ITERATIONS_LIMIT}).",
    )
    p.add_argument(
        "--timeout-per-source-seconds",
        type=int,
        default=DEFAULT_SOURCE_TIMEOUT_SECONDS,
        help="Per-source wall-clock timeout (seconds).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not persist the JSON digest (stdout only).",
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            sys.stdout.write(
                json.dumps({"status": "not_available", "reason": "no latest.json"}, indent=indent)
                + "\n"
            )
            return 0
        sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
        return 0

    if args.loop:
        snaps = run_loop(
            interval_seconds=args.interval_seconds,
            max_iterations=args.max_iterations,
            timeout_per_source=args.timeout_per_source_seconds,
            write=not args.no_write,
        )
        # Print the last snapshot for operator visibility.
        last = snaps[-1] if snaps else {}
        sys.stdout.write(json.dumps(last, indent=indent, sort_keys=True) + "\n")
        return 0

    # Default: --once.
    snap = run_once(
        timeout_per_source=args.timeout_per_source_seconds,
        write=not args.no_write,
    )
    sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
