"""v3.15 façade — paper validation engine.

Mirrors the v3.12 / v3.13 / v3.14 façade pattern: a frozen build
context + one ``build_and_write_*()`` entry point that the runner
calls once. Every artifact is written through
:func:`research._sidecar_io.write_sidecar_atomic` so the output
is canonical and byte-reproducible.

Produces four sidecars:

- ``research/candidate_timestamped_returns_latest.v1.json``
- ``research/paper_ledger_latest.v1.json``
- ``research/paper_divergence_latest.v1.json``
- ``research/paper_readiness_latest.v1.json``

The façade never writes to any v3.12 / v3.13 / v3.14 sidecar and
never imports anything from the live / broker execution stack.
v3.15 invariant: ``live_eligible=False`` in every payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from research._sidecar_io import write_sidecar_atomic
from research.asset_typing import normalize_asset_type
from research.candidate_registry_v2 import build_candidate_id
from research.candidate_timestamped_returns_feed import (
    TimestampedCandidateReturnsRecord,
    build_payload as build_timestamped_returns_payload,
    build_records_from_evaluations,
)
from research.paper_divergence import (
    CandidateDivergenceInput,
    build_paper_divergence_payload,
    compute_divergence,
)
from research.paper_ledger import (
    LedgerEvent,
    build_ledger_events_for_candidate,
    build_ledger_payload,
)
from research.paper_readiness import (
    PaperReadinessInput,
    build_paper_readiness_payload,
    compute_readiness,
)


TIMESTAMPED_RETURNS_PATH = Path(
    "research/candidate_timestamped_returns_latest.v1.json"
)
PAPER_LEDGER_PATH = Path("research/paper_ledger_latest.v1.json")
PAPER_DIVERGENCE_PATH = Path("research/paper_divergence_latest.v1.json")
PAPER_READINESS_PATH = Path("research/paper_readiness_latest.v1.json")


@dataclass(frozen=True)
class PaperValidationBuildContext:
    """Inputs the v3.15 façade needs.

    ``evaluations`` follows the shape of the runner's in-memory
    evaluations list (v3.14-compatible). Each entry may carry:

    - ``row`` with ``strategy_name`` / ``asset`` / ``interval`` /
      optionally ``asset_type`` / ``asset_class``
    - ``selected_params`` (or ``params_json`` under ``row``)
    - ``evaluation_report`` with:
        - ``evaluation_streams.oos_daily_returns`` (for
          timestamped returns)
        - ``evaluation_streams.oos_execution_events`` (for ledger)
        - ``kosten_per_kant`` at the evaluation-report top level
          (engine appends it; we read it defensively)
        - ``oos_summary`` (metrics) for baseline_final_equity +
          baseline_sharpe_proxy + baseline_max_drawdown

    ``sleeve_registry`` is the v3.14 sidecar payload (dict with
    ``memberships`` list). Only used for candidate_id → sleeve_id
    lookup.

    ``registry_v2`` is passed through to support asset_type
    resolution if the evaluation row lacks it.
    """

    run_id: str
    generated_at_utc: str
    git_revision: str
    registry_v2: dict[str, Any]
    sleeve_registry: dict[str, Any] | None
    evaluations: list[dict[str, Any]]
    # v3.15.4: optional Campaign Operating Layer ownership stamp.
    # Stored on the paper_readiness sidecar so the launcher can detect
    # a stale sidecar from a previous campaign (e.g. when the current
    # subprocess crashed before overwriting it). Null for direct CLI
    # invocations and back-compatible with v3.15-3.15.3 readers.
    col_campaign_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate_id_from_evaluation(evaluation: dict[str, Any]) -> str | None:
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
    return build_candidate_id(
        str(strategy_name),
        str(asset),
        str(interval),
        selected_params or {},
    )


def _asset_type_from_evaluation_or_registry(
    evaluation: dict[str, Any],
    registry_v2: dict[str, Any],
    candidate_id: str,
) -> str:
    row = evaluation.get("row") or {}
    for field in ("asset_type", "asset_class"):
        value = row.get(field) or evaluation.get(field)
        if value:
            return normalize_asset_type(asset_type=value, asset_class=value)
    # Fall back to registry_v2 entry lookup
    entries = registry_v2.get("entries") or []
    for entry in entries:
        if entry.get("candidate_id") == candidate_id:
            experiment_family = entry.get("experiment_family")
            asset_type = entry.get("asset_type")
            if asset_type:
                return normalize_asset_type(asset_type=asset_type)
            if isinstance(experiment_family, str) and "|" in experiment_family:
                _, asset_token = experiment_family.split("|", 1)
                return normalize_asset_type(asset_type=asset_token)
            break
    return "unknown"


def _sleeve_id_for_candidate(
    sleeve_registry: dict[str, Any] | None,
    candidate_id: str,
) -> str | None:
    if not sleeve_registry:
        return None
    memberships = sleeve_registry.get("memberships") or []
    for membership in memberships:
        if membership.get("candidate_id") == candidate_id:
            return membership.get("sleeve_id")
    return None


def _execution_events_from_evaluation(
    evaluation: dict[str, Any],
) -> list[Any]:
    report = evaluation.get("evaluation_report") or {}
    streams = report.get("evaluation_streams") or {}
    events = streams.get("oos_execution_events") or []
    return list(events)


def _count_full_fills(events: Iterable[Any]) -> int:
    count = 0
    for event in events:
        if isinstance(event, dict):
            kind = event.get("kind")
        else:
            kind = getattr(event, "kind", None)
        if kind == "full_fill":
            count += 1
    return count


def _baseline_metrics_from_report(
    evaluation_report: dict[str, Any] | None,
) -> tuple[float, float | None, float | None]:
    if not evaluation_report:
        return 1.0, None, None
    oos_summary = evaluation_report.get("oos_summary") or {}
    # eindkapitaal is the engine's final equity proxy; fall back to 1.0
    baseline_final_equity = oos_summary.get("eindkapitaal")
    if not isinstance(baseline_final_equity, (int, float)):
        baseline_final_equity = 1.0
    sharpe = oos_summary.get("sharpe")
    max_dd = oos_summary.get("max_drawdown")
    return (
        float(baseline_final_equity),
        float(sharpe) if isinstance(sharpe, (int, float)) else None,
        float(max_dd) if isinstance(max_dd, (int, float)) else None,
    )


def _kosten_per_kant_from_report(
    evaluation_report: dict[str, Any] | None,
) -> float:
    if not evaluation_report:
        return 0.0025
    kost = evaluation_report.get("kosten_per_kant")
    if isinstance(kost, (int, float)) and kost > 0.0:
        return float(kost)
    return 0.0025


def _count_projected_insufficient(events: Iterable[LedgerEvent]) -> int:
    return sum(
        1 for event in events
        if event.evidence_status == "projected_insufficient"
    )


# ---------------------------------------------------------------------------
# Façade entry
# ---------------------------------------------------------------------------


def build_and_write_paper_validation_sidecars(
    ctx: PaperValidationBuildContext,
    *,
    timestamped_returns_path: Path = TIMESTAMPED_RETURNS_PATH,
    paper_ledger_path: Path = PAPER_LEDGER_PATH,
    paper_divergence_path: Path = PAPER_DIVERGENCE_PATH,
    paper_readiness_path: Path = PAPER_READINESS_PATH,
) -> dict[str, Path]:
    """Produce and write every v3.15 sidecar atomically.

    Returns a dict mapping logical artifact name to its written
    path. Graceful empty/missing behaviour: when ``evaluations``
    is empty every sidecar is still written with a stable
    envelope and empty entries list.
    """
    paths: dict[str, Path] = {}

    # 1. Timestamped returns sidecar
    ts_records: list[TimestampedCandidateReturnsRecord] = (
        build_records_from_evaluations(ctx.evaluations)
    )
    ts_payload = build_timestamped_returns_payload(
        records=ts_records,
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
    )
    write_sidecar_atomic(timestamped_returns_path, ts_payload.to_payload())
    paths["candidate_timestamped_returns"] = timestamped_returns_path

    # 2. Build per-candidate derived data for ledger / divergence /
    #    readiness. We iterate once over evaluations.
    per_candidate_ledger: list[tuple[str, list[LedgerEvent]]] = []
    divergence_inputs: list[CandidateDivergenceInput] = []
    readiness_inputs: list[PaperReadinessInput] = []
    ts_records_by_id = {r.candidate_id: r for r in ts_records}
    by_candidate_seen: set[str] = set()

    for evaluation in ctx.evaluations:
        candidate_id = _candidate_id_from_evaluation(evaluation)
        if candidate_id is None:
            continue
        if candidate_id in by_candidate_seen:
            # Last-seen-wins mirrors build_records_from_evaluations,
            # but ledger/divergence would accumulate duplicates.
            # Overwrite prior entries by rebuilding them.
            per_candidate_ledger = [
                (cid, events) for cid, events in per_candidate_ledger
                if cid != candidate_id
            ]
            divergence_inputs = [
                i for i in divergence_inputs if i.candidate_id != candidate_id
            ]
            readiness_inputs = [
                i for i in readiness_inputs if i.candidate_id != candidate_id
            ]
        by_candidate_seen.add(candidate_id)

        asset_type = _asset_type_from_evaluation_or_registry(
            evaluation, ctx.registry_v2, candidate_id,
        )
        sleeve_id = _sleeve_id_for_candidate(ctx.sleeve_registry, candidate_id)

        execution_events = _execution_events_from_evaluation(evaluation)
        ledger_events = build_ledger_events_for_candidate(
            candidate_id=candidate_id,
            asset_type=asset_type,
            execution_events=execution_events,
        )
        per_candidate_ledger.append((candidate_id, ledger_events))

        report = evaluation.get("evaluation_report") or {}
        baseline_final_equity, baseline_sharpe, baseline_max_dd = (
            _baseline_metrics_from_report(report)
        )
        kosten_per_kant = _kosten_per_kant_from_report(report)
        n_full_fills = _count_full_fills(execution_events)
        tsr = ts_records_by_id.get(candidate_id)

        divergence_inputs.append(CandidateDivergenceInput(
            candidate_id=candidate_id,
            asset_type=asset_type,
            sleeve_id=sleeve_id,
            baseline_kosten_per_kant=kosten_per_kant,
            n_full_fills=n_full_fills,
            baseline_final_equity=baseline_final_equity,
            baseline_sharpe_proxy=baseline_sharpe,
            baseline_max_drawdown=baseline_max_dd,
            timestamped_returns=tsr,
        ))

        projected_insufficient = _count_projected_insufficient(ledger_events)
        readiness_inputs.append(PaperReadinessInput(
            candidate_id=candidate_id,
            asset_type=asset_type,
            sleeve_id=sleeve_id,
            timestamped_returns=tsr,
            ledger_event_count=len(ledger_events),
            projected_insufficient_event_count=projected_insufficient,
            divergence_entry=None,  # filled after divergence computes
            paper_sharpe_proxy=baseline_sharpe,  # v0.1 proxy
        ))

    # 3. Divergence body
    divergence_body = compute_divergence(
        candidates=divergence_inputs,
        timestamped_returns=ts_records,
    )
    divergence_payload = build_paper_divergence_payload(
        body=divergence_body,
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
    )

    # 4. Paper ledger sidecar
    ledger_payload = build_ledger_payload(
        entries=per_candidate_ledger,
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
    )
    write_sidecar_atomic(paper_ledger_path, ledger_payload)
    paths["paper_ledger"] = paper_ledger_path

    # 5. Divergence sidecar
    write_sidecar_atomic(paper_divergence_path, divergence_payload)
    paths["paper_divergence"] = paper_divergence_path

    # 6. Readiness sidecar — needs divergence entries threaded in
    divergence_by_candidate: dict[str, dict[str, Any]] = {
        entry["candidate_id"]: entry
        for entry in divergence_body.get("per_candidate", [])
    }
    readiness_with_divergence = [
        PaperReadinessInput(
            candidate_id=ri.candidate_id,
            asset_type=ri.asset_type,
            sleeve_id=ri.sleeve_id,
            timestamped_returns=ri.timestamped_returns,
            ledger_event_count=ri.ledger_event_count,
            projected_insufficient_event_count=ri.projected_insufficient_event_count,
            divergence_entry=divergence_by_candidate.get(ri.candidate_id),
            paper_sharpe_proxy=ri.paper_sharpe_proxy,
        )
        for ri in readiness_inputs
    ]
    readiness_entries = compute_readiness(readiness_with_divergence)
    readiness_payload = build_paper_readiness_payload(
        entries=readiness_entries,
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
        col_campaign_id=ctx.col_campaign_id,
    )
    write_sidecar_atomic(paper_readiness_path, readiness_payload)
    paths["paper_readiness"] = paper_readiness_path

    return paths


__all__ = [
    "PAPER_DIVERGENCE_PATH",
    "PAPER_LEDGER_PATH",
    "PAPER_READINESS_PATH",
    "TIMESTAMPED_RETURNS_PATH",
    "PaperValidationBuildContext",
    "build_and_write_paper_validation_sidecars",
]
