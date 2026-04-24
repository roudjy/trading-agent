"""v3.15 per-candidate timestamped daily-returns bridge.

v3.14 shipped a per-candidate *untimestamped* return bridge
(:mod:`research.candidate_returns_feed`) that uses the engine's
aggregated ``evaluation_samples.daily_returns`` list. v3.14
handoff §8.1 flagged this as a precision gap: correlations and
paper-level aggregations can only align on suffix length, not
on actual dates.

v3.15 closes that gap with an **additive** sidecar. It consumes
the typed stream already emitted by the engine at
``engine.last_evaluation_report["evaluation_streams"]["oos_daily_returns"]``
— a list of ``{timestamp_utc, return}`` points — validated through
:func:`research._oos_stream.normalize_oos_daily_return_stream`.

The v3.14 frozen sidecar (``candidate_returns_latest.v1.json``) is
**not** mutated. This module writes a separate sidecar:

    research/candidate_timestamped_returns_latest.v1.json

Schema (``schema_version="1.0"``):

- ``alignment`` = ``"utc_daily_close"``
- ``timestamp_semantics`` = ``"engine_window_close_utc"``
- ``entries[*]`` = per-candidate record with ``timestamps`` and
  ``daily_returns`` arrays of equal length, plus explicit
  stream-normalization error code when the stream failed
  validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from research._oos_stream import normalize_oos_daily_return_stream
from research.candidate_registry_v2 import build_candidate_id


TIMESTAMPED_RETURNS_ALIGNMENT: str = "utc_daily_close"
TIMESTAMPED_RETURNS_TIMESTAMP_SEMANTICS: str = "engine_window_close_utc"
TIMESTAMPED_RETURNS_SCHEMA_VERSION: str = "1.0"


@dataclass(frozen=True)
class TimestampedCandidateReturnsRecord:
    """Per-candidate typed timestamped return record.

    ``timestamps`` and ``daily_returns`` have equal length when
    ``insufficient_returns`` is ``False``. When the engine
    stream was missing or malformed ``stream_error`` carries the
    error code from
    :mod:`research._oos_stream` and both arrays are empty.
    """

    candidate_id: str
    timestamps: tuple[str, ...]
    daily_returns: tuple[float, ...]
    n_obs: int
    start_date: str | None
    end_date: str | None
    alignment: str = TIMESTAMPED_RETURNS_ALIGNMENT
    insufficient_returns: bool = False
    stream_error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "timestamps": list(self.timestamps),
            "daily_returns": list(self.daily_returns),
            "n_obs": int(self.n_obs),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "alignment": self.alignment,
            "insufficient_returns": bool(self.insufficient_returns),
            "stream_error": self.stream_error,
        }


@dataclass(frozen=True)
class TimestampedCandidateReturnsPayload:
    """The full sidecar-shaped payload."""

    schema_version: str
    generated_at_utc: str
    run_id: str
    git_revision: str
    alignment: str
    timestamp_semantics: str
    entries: list[TimestampedCandidateReturnsRecord] = field(default_factory=list)

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


def _extract_raw_stream(
    evaluation_report: dict[str, Any] | None,
) -> Any:
    if not evaluation_report:
        return None
    streams = evaluation_report.get("evaluation_streams") or {}
    return streams.get("oos_daily_returns")


def build_record_from_evaluation(
    evaluation: dict[str, Any],
) -> TimestampedCandidateReturnsRecord | None:
    """Turn one entry of ``run_research.run_research.evaluations`` into a
    :class:`TimestampedCandidateReturnsRecord`.

    Returns ``None`` when the entry lacks a resolvable strategy-name
    tuple (mirrors :mod:`research.candidate_returns_feed`).
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
    raw_stream = _extract_raw_stream(evaluation.get("evaluation_report"))
    stream, err = normalize_oos_daily_return_stream(raw_stream)
    if err is not None or not stream:
        return TimestampedCandidateReturnsRecord(
            candidate_id=candidate_id,
            timestamps=(),
            daily_returns=(),
            n_obs=0,
            start_date=None,
            end_date=None,
            alignment=TIMESTAMPED_RETURNS_ALIGNMENT,
            insufficient_returns=True,
            stream_error=err,
        )
    timestamps = tuple(point["timestamp_utc"] for point in stream)
    returns = tuple(float(point["return"]) for point in stream)
    return TimestampedCandidateReturnsRecord(
        candidate_id=candidate_id,
        timestamps=timestamps,
        daily_returns=returns,
        n_obs=len(returns),
        start_date=timestamps[0],
        end_date=timestamps[-1],
        alignment=TIMESTAMPED_RETURNS_ALIGNMENT,
        insufficient_returns=False,
        stream_error=None,
    )


def build_records_from_evaluations(
    evaluations: Iterable[dict[str, Any]],
) -> list[TimestampedCandidateReturnsRecord]:
    """Iterate over the runner's ``evaluations`` list and emit a sorted,
    deduplicated list. Duplicates (same ``candidate_id``) keep the last
    seen record.
    """
    by_id: dict[str, TimestampedCandidateReturnsRecord] = {}
    for evaluation in evaluations:
        record = build_record_from_evaluation(evaluation)
        if record is None:
            continue
        by_id[record.candidate_id] = record
    return sorted(by_id.values(), key=lambda r: r.candidate_id)


def build_payload(
    *,
    records: list[TimestampedCandidateReturnsRecord],
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
) -> TimestampedCandidateReturnsPayload:
    """Assemble the sidecar payload from a list of records."""
    return TimestampedCandidateReturnsPayload(
        schema_version=TIMESTAMPED_RETURNS_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        run_id=run_id,
        git_revision=git_revision,
        alignment=TIMESTAMPED_RETURNS_ALIGNMENT,
        timestamp_semantics=TIMESTAMPED_RETURNS_TIMESTAMP_SEMANTICS,
        entries=list(records),
    )


__all__ = [
    "TIMESTAMPED_RETURNS_ALIGNMENT",
    "TIMESTAMPED_RETURNS_SCHEMA_VERSION",
    "TIMESTAMPED_RETURNS_TIMESTAMP_SEMANTICS",
    "TimestampedCandidateReturnsRecord",
    "TimestampedCandidateReturnsPayload",
    "build_record_from_evaluation",
    "build_records_from_evaluations",
    "build_payload",
]
