"""Throughput and runtime metrics observability module.

Reads campaign registry + queue (JSON) and computes campaigns-per-day,
runtime distributions, success/degenerate/failure rates, queue waits,
worker utilization. Pure aggregation. Deterministic given the input
payloads + ``now_utc``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from research._sidecar_io import write_sidecar_atomic

from .clock import default_now_utc, to_iso_z
from .io import read_json_safe
from .paths import (
    CAMPAIGN_REGISTRY_PATH,
    OBSERVABILITY_SCHEMA_VERSION,
    RESEARCH_DIR,
    THROUGHPUT_METRICS_PATH,
)

CAMPAIGN_QUEUE_PATH: Path = RESEARCH_DIR / "campaign_queue_latest.v1.json"
CAMPAIGN_DIGEST_PATH: Path = RESEARCH_DIR / "campaign_digest_latest.v1.json"


# --- Pure helpers ---------------------------------------------------------


def _percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolation percentile. Deterministic for sorted input.

    Returns None for empty input. Always sorts a copy of the list to
    avoid mutating caller data.
    """
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    s = sorted(values)
    n = len(s)
    rank = (n - 1) * (p / 100.0)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def _to_numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_iso_utc(s: Any) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        # Tolerate Z-suffix.
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00")
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _campaigns(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("campaigns")
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, dict):
        return [c for c in raw.values() if isinstance(c, dict)]
    return []


def _runtime_min_value(record: dict[str, Any]) -> float | None:
    for key in ("runtime_min", "runtime_minutes"):
        v = _to_numeric(record.get(key))
        if v is not None:
            return v
    started = _parse_iso_utc(record.get("started_at_utc") or record.get("started_at"))
    finished = _parse_iso_utc(
        record.get("finished_at_utc")
        or record.get("finished_at")
        or record.get("completed_at_utc")
    )
    if started is not None and finished is not None and finished >= started:
        return (finished - started).total_seconds() / 60.0
    return None


def _queue_wait_seconds(record: dict[str, Any]) -> float | None:
    queued = _parse_iso_utc(record.get("queued_at_utc") or record.get("queued_at"))
    started = _parse_iso_utc(record.get("started_at_utc") or record.get("started_at"))
    if queued is None or started is None or started < queued:
        return None
    return (started - queued).total_seconds()


def _is_meaningful(record: dict[str, Any]) -> bool:
    """Conservative ``meaningful_campaign`` definition.

    Per the brief:
      * completed with valid research evidence
      * completed no-survivor with valid evidence
      * research rejection with explainable failure reason
      * completed funnel stage with evidence artifact

    NOT meaningful:
      * worker crashes without usable evidence
      * malformed campaign records
      * missing-artifact failures

    v3.15.15.4 extends the recognised vocabulary to include the
    launcher's actual outcome literals (research/campaign_launcher.py
    ~lines 1378-1453, v3.15.5+). Existing semantics for ``completed``
    / ``no_signal`` / ``near_pass`` / ``failed`` are unchanged — a
    regression test pins those mappings.
    """
    outcome = record.get("outcome")
    # Always meaningful — campaign produced research evidence we can learn from.
    if outcome in (
        "no_signal",
        "near_pass",
        "completed",
        "completed_with_candidates",
        "completed_no_survivor",
        "research_rejection",
        "degenerate_no_survivors",
        "paper_blocked",
    ):
        return True
    # Failed-class with explainable, non-crash reason → meaningful.
    if outcome == "failed":
        reason = record.get("failure_reason")
        if isinstance(reason, str) and reason:
            crash_reasons = {"worker_crash", "lease_lost", "missing_artifact"}
            return reason not in crash_reasons
    # Launcher-literal technical / integrity / worker_crashed: NOT meaningful.
    if outcome in ("technical_failure", "worker_crashed", "integrity_failed"):
        return False
    # Cancellations: not meaningful.
    if outcome in (
        "canceled",
        "aborted",
        "canceled_duplicate",
        "canceled_upstream_stale",
    ):
        return False
    return False


def _campaigns_in_window(
    records: Iterable[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in records:
        finished = _parse_iso_utc(
            r.get("finished_at_utc")
            or r.get("finished_at")
            or r.get("completed_at_utc")
        )
        if finished is None:
            continue
        if window_start <= finished <= window_end:
            out.append(r)
    return out


# --- Public aggregation ---------------------------------------------------


def compute_throughput_metrics(
    *,
    registry_payload: Any | None = None,
    queue_payload: Any | None = None,
    digest_payload: Any | None = None,
    registry_state: str | None = None,
    queue_state: str | None = None,
    digest_state: str | None = None,
    now_utc: datetime | None = None,
    window_days: int = 1,
) -> dict[str, Any]:
    when = now_utc or default_now_utc()
    window_end = when
    window_start = when - timedelta(days=window_days)

    campaigns = _campaigns(registry_payload)
    in_window = _campaigns_in_window(
        campaigns,
        window_start=window_start,
        window_end=window_end,
    )

    runtimes = [
        v for v in (_runtime_min_value(c) for c in in_window) if v is not None
    ]
    queue_waits = [
        v for v in (_queue_wait_seconds(c) for c in in_window) if v is not None
    ]

    outcome_counter: Counter[str] = Counter()
    for c in in_window:
        outcome = c.get("outcome")
        if isinstance(outcome, str) and outcome:
            outcome_counter[outcome] += 1

    completed = outcome_counter.get("completed", 0)
    no_signal = outcome_counter.get("no_signal", 0)
    near_pass = outcome_counter.get("near_pass", 0)
    failed = outcome_counter.get("failed", 0)
    canceled = outcome_counter.get("canceled", 0)
    running = outcome_counter.get("running", 0)
    total_in_window = len(in_window)

    meaningful = sum(1 for c in in_window if _is_meaningful(c))

    success_rate = (
        (completed + no_signal + near_pass) / total_in_window
        if total_in_window
        else None
    )
    degenerate_rate = (
        outcome_counter.get("no_signal", 0) / total_in_window
        if total_in_window
        else None
    )
    research_rejection_rate = (
        (no_signal + near_pass) / total_in_window if total_in_window else None
    )
    technical_failure_rate = (
        failed / total_in_window if total_in_window else None
    )

    # Per-preset / per-timeframe runtime
    by_preset: dict[str, list[float]] = {}
    by_timeframe: dict[str, list[float]] = {}
    by_campaign_type: dict[str, list[float]] = {}
    for c in in_window:
        rt = _runtime_min_value(c)
        if rt is None:
            continue
        preset = c.get("preset") or c.get("preset_name")
        if isinstance(preset, str):
            by_preset.setdefault(preset, []).append(rt)
        timeframe = c.get("timeframe")
        if isinstance(timeframe, str):
            by_timeframe.setdefault(timeframe, []).append(rt)
        ct = c.get("campaign_type")
        if isinstance(ct, str):
            by_campaign_type.setdefault(ct, []).append(rt)

    def _avg_table(buckets: dict[str, list[float]]) -> list[dict[str, float | str]]:
        rows = [
            {
                "name": name,
                "count": len(vals),
                "avg_min": round(sum(vals) / len(vals), 4) if vals else 0.0,
                "p50_min": round(_percentile(vals, 50) or 0.0, 4),
                "p95_min": round(_percentile(vals, 95) or 0.0, 4),
            }
            for name, vals in buckets.items()
        ]
        rows.sort(key=lambda x: (-x["count"], x["name"]))
        return rows

    queue_depth: int | None = None
    workers_busy: int | None = None
    workers_total: int | None = None
    stale_lease_count: int | None = None
    queue_backpressure_flag: bool | None = None

    if isinstance(queue_payload, dict):
        q = queue_payload.get("queue")
        if isinstance(q, list):
            queue_depth = len(q)
        wb = queue_payload.get("workers_busy")
        wt = queue_payload.get("workers_total")
        if isinstance(wb, int):
            workers_busy = wb
        if isinstance(wt, int):
            workers_total = wt
        sl = queue_payload.get("stale_lease_count")
        if isinstance(sl, int):
            stale_lease_count = sl
        bp = queue_payload.get("queue_backpressure")
        if isinstance(bp, bool):
            queue_backpressure_flag = bp

    if isinstance(digest_payload, dict):
        if queue_depth is None:
            qd = digest_payload.get("queue_depth")
            if isinstance(qd, int):
                queue_depth = qd
        if workers_busy is None:
            wb = digest_payload.get("workers_busy")
            if isinstance(wb, int):
                workers_busy = wb
        if workers_total is None:
            wt = digest_payload.get("workers_total")
            if isinstance(wt, int):
                workers_total = wt

    busy_rate: float | None = None
    if workers_busy is not None and workers_total:
        busy_rate = round(workers_busy / workers_total, 4)
    idle_rate = (
        round(1.0 - busy_rate, 4) if busy_rate is not None else None
    )

    # v3.15.15.6 — digest passthroughs. Tagged ``_from_digest`` so
    # consumers know these counts came from the launcher's per-tick
    # digest aggregation, not from this module's own recompute.
    meaningful_by_classification_from_digest: dict[str, int] | None = None
    campaigns_by_type_from_digest: dict[str, int] | None = None
    if isinstance(digest_payload, dict):
        mbc = digest_payload.get("meaningful_by_classification")
        if isinstance(mbc, dict):
            meaningful_by_classification_from_digest = {
                str(k): int(v)
                for k, v in mbc.items()
                if isinstance(v, (int, float))
            }
        cbt = digest_payload.get("campaigns_by_type")
        if isinstance(cbt, dict):
            campaigns_by_type_from_digest = {
                str(k): int(v)
                for k, v in cbt.items()
                if isinstance(v, (int, float))
            }

    return {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "generated_at_utc": to_iso_z(when),
        "window": {
            "days": window_days,
            "start_utc": to_iso_z(window_start),
            "end_utc": to_iso_z(window_end),
        },
        "source": {
            "registry_state": registry_state,
            "queue_state": queue_state,
            "digest_state": digest_state,
            "campaigns_observed_in_registry": len(campaigns),
            "campaigns_in_window": total_in_window,
        },
        "campaigns_per_day": round(total_in_window / window_days, 4),
        "completed_campaigns_per_day": round(completed / window_days, 4),
        "meaningful_campaigns_per_day": round(meaningful / window_days, 4),
        "outcomes": dict(sorted(outcome_counter.items())),
        "success_rate": success_rate,
        "degenerate_rate": degenerate_rate,
        "research_rejection_rate": research_rejection_rate,
        "technical_failure_rate": technical_failure_rate,
        "runtime_minutes": {
            "count": len(runtimes),
            "p50": round(_percentile(runtimes, 50) or 0.0, 4),
            "p95": round(_percentile(runtimes, 95) or 0.0, 4),
            "avg": round(sum(runtimes) / len(runtimes), 4) if runtimes else None,
        },
        "queue_wait_seconds": {
            "count": len(queue_waits),
            "p50": round(_percentile(queue_waits, 50) or 0.0, 4),
            "p95": round(_percentile(queue_waits, 95) or 0.0, 4),
        },
        "runtime_by_preset": _avg_table(by_preset),
        "runtime_by_timeframe": _avg_table(by_timeframe),
        "runtime_by_campaign_type": _avg_table(by_campaign_type),
        "workers": {
            "busy": workers_busy,
            "total": workers_total,
            "busy_rate": busy_rate,
            "idle_rate": idle_rate,
        },
        "queue": {
            "depth": queue_depth,
            "stale_lease_count": stale_lease_count,
            "backpressure_flag": queue_backpressure_flag,
        },
        "running_count": running,
        "canceled_count": canceled,
        "running_canceled_excluded_from_meaningful": True,
        # v3.15.15.6 digest passthroughs (None when digest is absent).
        "meaningful_by_classification_from_digest": meaningful_by_classification_from_digest,
        "campaigns_by_type_from_digest": campaigns_by_type_from_digest,
    }


def build_throughput_artifact(
    *,
    now_utc: datetime | None = None,
    registry_path: Path = CAMPAIGN_REGISTRY_PATH,
    queue_path: Path = CAMPAIGN_QUEUE_PATH,
    digest_path: Path = CAMPAIGN_DIGEST_PATH,
    window_days: int = 1,
) -> dict[str, Any]:
    registry = read_json_safe(registry_path)
    queue = read_json_safe(queue_path)
    digest = read_json_safe(digest_path)
    return compute_throughput_metrics(
        registry_payload=registry.payload if registry.state == "valid" else None,
        queue_payload=queue.payload if queue.state == "valid" else None,
        digest_payload=digest.payload if digest.state == "valid" else None,
        registry_state=registry.state,
        queue_state=queue.state,
        digest_state=digest.state,
        now_utc=now_utc,
        window_days=window_days,
    )


def write_throughput(
    payload: dict[str, Any],
    *,
    path: Path | None = None,
) -> None:
    target = path if path is not None else THROUGHPUT_METRICS_PATH
    if "observability" not in str(target).replace("\\", "/").split("/"):
        raise RuntimeError(
            "write_throughput refuses to write outside research/observability/"
        )
    write_sidecar_atomic(target, payload)


__all__ = [
    "build_throughput_artifact",
    "compute_throughput_metrics",
    "write_throughput",
]
