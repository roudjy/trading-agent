"""v3.14 per-candidate daily-returns bridge.

Per-candidate daily return series are not persisted anywhere in
the v3.12/v3.13 artifact graph. They are produced transiently in
``BacktestEngine._last_window_samples["daily_returns"]`` and exposed
through ``engine.last_evaluation_report.evaluation_samples.daily_returns``.

v3.14 portfolio/sleeve diagnostics need real return series for
correlation and drawdown-attribution research. This module defines
the smallest typed bridge that extracts those series from the
validation ``evaluations`` list already collected in
``run_research.run_research`` and turns them into a deterministic
sidecar.

Determinism policy:

- ``alignment = "utc_daily_close"`` — sourced directly from the
  engine's window-close timestamps.
- Entries are sorted by ``candidate_id``.
- ``insufficient_returns=True`` when the evaluation report carries
  no daily returns (e.g. short validation window).

The bridge is intentionally one-way: it never mutates engine or
registry state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from research.candidate_registry_v2 import build_candidate_id


RETURNS_ALIGNMENT = "utc_daily_close"
RETURNS_TIMESTAMP_SEMANTICS = "engine_window_close_utc"
RETURNS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class CandidateReturnsRecord:
    """Canonical per-candidate return record."""

    candidate_id: str
    daily_returns: tuple[float, ...]
    n_obs: int
    start_date: str | None
    end_date: str | None
    alignment: str = RETURNS_ALIGNMENT
    insufficient_returns: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "daily_returns": list(self.daily_returns),
            "n_obs": int(self.n_obs),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "alignment": self.alignment,
            "insufficient_returns": bool(self.insufficient_returns),
        }


@dataclass(frozen=True)
class CandidateReturnsPayload:
    """The full sidecar-shaped payload."""

    schema_version: str
    generated_at_utc: str
    run_id: str
    git_revision: str
    alignment: str
    timestamp_semantics: str
    entries: list[CandidateReturnsRecord] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at_utc": self.generated_at_utc,
            "run_id": self.run_id,
            "git_revision": self.git_revision,
            "alignment": self.alignment,
            "timestamp_semantics": self.timestamp_semantics,
            "entries": [e.to_payload() for e in self.entries],
        }


def _extract_daily_returns(evaluation_report: dict[str, Any] | None) -> tuple[float, ...]:
    if not evaluation_report:
        return ()
    samples = evaluation_report.get("evaluation_samples") or {}
    raw = samples.get("daily_returns") or []
    result: list[float] = []
    for value in raw:
        try:
            result.append(float(value))
        except (TypeError, ValueError):
            continue
    return tuple(result)


def _extract_fold_boundaries(evaluation_report: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Best-effort start/end-date extraction from the evaluation report.

    Looks at ``folds_by_asset`` when present, otherwise falls back to
    None. Dates are stringified as-is; the engine already emits ISO.
    """
    if not evaluation_report:
        return None, None
    folds_by_asset = evaluation_report.get("folds_by_asset") or {}
    start: str | None = None
    end: str | None = None
    for folds in folds_by_asset.values():
        for fold in folds or []:
            train_range = fold.get("train") if isinstance(fold, dict) else None
            test_range = fold.get("test") if isinstance(fold, dict) else None
            lows = [r for r in (train_range, test_range) if isinstance(r, (list, tuple)) and len(r) == 2]
            for low, high in lows:
                if low is not None and (start is None or str(low) < start):
                    start = str(low)
                if high is not None and (end is None or str(high) > end):
                    end = str(high)
    return start, end


def build_record_from_evaluation(evaluation: dict[str, Any]) -> CandidateReturnsRecord | None:
    """Turn one entry of ``run_research.run_research.evaluations`` into
    a :class:`CandidateReturnsRecord`.

    The entry must carry ``evaluation_report`` (populated via
    ``engine.last_evaluation_report``) and enough identifiers to
    reconstruct a :func:`~research.candidate_registry_v2.build_candidate_id`.
    Returns ``None`` when the entry lacks a resolvable strategy-name
    tuple (defensive, mirrors engine behaviour).
    """
    row = evaluation.get("row") or {}
    strategy_name = row.get("strategy_name") or evaluation.get("strategy_name")
    asset = row.get("asset") or evaluation.get("asset")
    interval = row.get("interval") or evaluation.get("interval")
    selected_params = evaluation.get("selected_params")
    if selected_params is None:
        params_json = row.get("params_json")
        if isinstance(params_json, str):
            try:
                selected_params = json.loads(params_json)
            except json.JSONDecodeError:
                selected_params = None
    if strategy_name is None or asset is None or interval is None:
        return None
    candidate_id = build_candidate_id(
        str(strategy_name),
        str(asset),
        str(interval),
        selected_params or {},
    )
    evaluation_report = evaluation.get("evaluation_report")
    returns = _extract_daily_returns(evaluation_report)
    start_date, end_date = _extract_fold_boundaries(evaluation_report)
    return CandidateReturnsRecord(
        candidate_id=candidate_id,
        daily_returns=returns,
        n_obs=len(returns),
        start_date=start_date,
        end_date=end_date,
        alignment=RETURNS_ALIGNMENT,
        insufficient_returns=len(returns) == 0,
    )


def build_records_from_evaluations(
    evaluations: Iterable[dict[str, Any]],
) -> list[CandidateReturnsRecord]:
    """Iterate over the runner's ``evaluations`` list and emit a
    sorted, deduplicated list of :class:`CandidateReturnsRecord`.

    Duplicates (same ``candidate_id``) keep the last seen record so
    deterministic ordering requires the caller to pass a deterministic
    iterable.
    """
    by_id: dict[str, CandidateReturnsRecord] = {}
    for evaluation in evaluations:
        record = build_record_from_evaluation(evaluation)
        if record is None:
            continue
        by_id[record.candidate_id] = record
    return sorted(by_id.values(), key=lambda r: r.candidate_id)


def build_payload(
    *,
    records: list[CandidateReturnsRecord],
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
) -> CandidateReturnsPayload:
    """Assemble the sidecar payload from a list of records."""
    return CandidateReturnsPayload(
        schema_version=RETURNS_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        run_id=run_id,
        git_revision=git_revision,
        alignment=RETURNS_ALIGNMENT,
        timestamp_semantics=RETURNS_TIMESTAMP_SEMANTICS,
        entries=list(records),
    )


__all__ = [
    "RETURNS_ALIGNMENT",
    "RETURNS_SCHEMA_VERSION",
    "RETURNS_TIMESTAMP_SEMANTICS",
    "CandidateReturnsRecord",
    "CandidateReturnsPayload",
    "build_record_from_evaluation",
    "build_records_from_evaluations",
    "build_payload",
]
