"""Execution adapter for controlled discovery grid rows.

This module maps a planned discovery-grid combination onto a bounded,
single-asset research preset override that can be executed through the
existing ``research.run_research`` path. Unsupported behavior families
do not raise as normal control flow; they return a deterministic
``skipped`` blocker result instead.
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from research.presets import ResearchPreset
from research.production_discovery_catalog import list_presets


REQUIRED_GRID_FIELDS: Final[tuple[str, ...]] = (
    "sequence_number",
    "instrument_symbol",
    "canonical_instrument_id",
    "region",
    "asset_class",
    "behavior_preset_id",
    "hypothesis_id",
    "timeframe",
)

BLOCKER_UNSUPPORTED_MAPPING: Final[str] = "unsupported_grid_to_validation_mapping"
BLOCKER_MISSING_METADATA: Final[str] = "missing_validation_input"
BLOCKER_SAFETY_VIOLATION: Final[str] = "blocked_by_safety"
BLOCKER_REGION_MISMATCH: Final[str] = "preset_region_constraint_mismatch"
BLOCKER_ASSET_CLASS_MISMATCH: Final[str] = "preset_asset_class_constraint_mismatch"
BLOCKER_CONTROLLED_VALIDATION_FAILED: Final[str] = "controlled_validation_failed"
BLOCKER_UNKNOWN_EXECUTION_ERROR: Final[str] = "unknown_execution_error"

RESULT_REPORT_KIND: Final[str] = "qre_controlled_discovery_grid_execution_result"


@dataclass(frozen=True)
class ExecutionTemplate:
    behavior_preset_id: str
    preset_reference: str
    bundle: tuple[str, ...]
    screening_phase: str
    executable_hypothesis_id: str | None
    executable: bool
    supported_asset_classes: tuple[str, ...]
    supported_regions: tuple[str, ...]
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class GridExecutionMapping:
    status: str
    blocker_class: str | None
    validation_campaign_id: str
    strategy_or_preset_reference: str | None
    asset_symbol: str
    timeframe: str | None
    hypothesis_id: str | None
    run_label: str
    output_subdir: str
    safety_flags: dict[str, bool]
    mapping_notes: tuple[str, ...]
    preset_override: ResearchPreset | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "blocker_class": self.blocker_class,
            "validation_campaign_id": self.validation_campaign_id,
            "strategy_or_preset_reference": self.strategy_or_preset_reference,
            "asset_symbol": self.asset_symbol,
            "timeframe": self.timeframe,
            "hypothesis_id": self.hypothesis_id,
            "run_label": self.run_label,
            "output_subdir": self.output_subdir,
            "safety_flags": dict(self.safety_flags),
            "mapping_notes": list(self.mapping_notes),
        }


@dataclass(frozen=True)
class GridExecutionObservation:
    status: str
    outcome_class: str
    blocker_class: str | None
    error_class: str | None
    trades_total: float | None
    oos_trades: int | None
    hd_trades: float | None
    criteria_status: str | None
    promotion_candidate: bool
    near_pass: bool
    safe_to_promote: bool
    artifact_paths: dict[str, str]
    candidate_count: int
    started_at_utc: str
    finished_at_utc: str
    duration_seconds: float
    execution_notes: tuple[str, ...]


_CATALOG_PRESET_BY_ID: Final[dict[str, dict[str, Any]]] = {
    str(preset.to_payload()["preset_id"]): preset.to_payload()
    for preset in list_presets()
}

_EXECUTION_TEMPLATES: Final[dict[str, ExecutionTemplate]] = {
    "trend_continuation_daily_v1": ExecutionTemplate(
        behavior_preset_id="trend_continuation_daily_v1",
        preset_reference="trend_equities_4h_baseline",
        bundle=("sma_crossover", "breakout_momentum"),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=True,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
    ),
    "trend_pullback_continuation_daily_v1": ExecutionTemplate(
        behavior_preset_id="trend_pullback_continuation_daily_v1",
        preset_reference="trend_pullback_equities_4h",
        bundle=("trend_pullback_v1",),
        screening_phase="exploratory",
        executable_hypothesis_id="trend_pullback_v1",
        executable=True,
        supported_asset_classes=("equity",),
        supported_regions=("NL/EU", "US", "Asia/proxies"),
    ),
    "vol_compression_breakout_daily_v1": ExecutionTemplate(
        behavior_preset_id="vol_compression_breakout_daily_v1",
        preset_reference="vol_compression_breakout_crypto_1h",
        bundle=("volatility_compression_breakout",),
        screening_phase="exploratory",
        executable_hypothesis_id="volatility_compression_breakout_v0",
        executable=True,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
    ),
    "vol_compression_breakout_4h_v1": ExecutionTemplate(
        behavior_preset_id="vol_compression_breakout_4h_v1",
        preset_reference="vol_compression_breakout_crypto_4h",
        bundle=("volatility_compression_breakout",),
        screening_phase="exploratory",
        executable_hypothesis_id="volatility_compression_breakout_v0",
        executable=True,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("US", "ETFs/context"),
    ),
    "relative_strength_vs_sector_daily_v1": ExecutionTemplate(
        behavior_preset_id="relative_strength_vs_sector_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity",),
        supported_regions=("NL/EU", "US"),
        unsupported_reason="preset_not_executable",
    ),
    "relative_strength_vs_region_daily_v1": ExecutionTemplate(
        behavior_preset_id="relative_strength_vs_region_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        unsupported_reason="preset_not_executable",
    ),
    "post_shock_stabilization_daily_v1": ExecutionTemplate(
        behavior_preset_id="post_shock_stabilization_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        unsupported_reason="preset_not_executable",
    ),
    "index_regime_filter_daily_v1": ExecutionTemplate(
        behavior_preset_id="index_regime_filter_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        unsupported_reason="preset_not_executable",
    ),
}


def _missing_required_fields(row: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_GRID_FIELDS if row.get(field) in (None, "", [])]


def _safety_flags(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "not_alpha_claim": bool(row.get("not_alpha_claim") is True),
        "paper_activation_allowed": bool(row.get("paper_activation_allowed") is True),
        "shadow_activation_allowed": bool(row.get("shadow_activation_allowed") is True),
        "live_activation_allowed": bool(row.get("live_activation_allowed") is True),
    }


def _deterministic_ids(row: dict[str, Any]) -> tuple[str, str, str]:
    sequence = int(row["sequence_number"])
    symbol = str(row["instrument_symbol"])
    preset_id = str(row["behavior_preset_id"])
    validation_campaign_id = (
        f"qre-grid-validation-{sequence:03d}-{symbol.lower()}-{preset_id}"
    )
    run_label = f"qre_grid_seq_{sequence:03d}_{symbol}_{preset_id}"
    output_subdir = f"combination_{sequence:03d}_{symbol}_{preset_id}"
    return validation_campaign_id, run_label, output_subdir


def _preset_override_for(
    *,
    row: dict[str, Any],
    template: ExecutionTemplate,
) -> ResearchPreset:
    symbol = str(row["instrument_symbol"])
    timeframe = str(row["timeframe"])
    hypothesis_id = (
        template.executable_hypothesis_id
        if template.executable_hypothesis_id is not None
        else None
    )
    return ResearchPreset(
        name=f"qre_grid_exec__{row['sequence_number']:03d}__{symbol}__{template.behavior_preset_id}",
        hypothesis=(
            "Controlled discovery grid execution override. This is a "
            "single-asset bounded research attempt; it is not an alpha claim "
            "and grants no paper/shadow/live authority."
        ),
        universe=(symbol,),
        timeframe=timeframe,
        bundle=template.bundle,
        screening_mode="strict",
        screening_phase=template.screening_phase,  # type: ignore[arg-type]
        cost_mode="realistic",
        status="stable",
        enabled=True,
        diagnostic_only=False,
        excluded_from_daily_scheduler=True,
        excluded_from_candidate_promotion=False,
        hypothesis_id=hypothesis_id,
        preset_class="experimental",
        rationale=(
            "Bounded controlled discovery-grid execution over an existing "
            "executable strategy bundle."
        ),
        expected_behavior=(
            "Produces per-combination research evidence using the existing "
            "run_research path with a single-asset universe override."
        ),
        falsification=(
            "No executable candidates emerge for the mapped asset/timeframe.",
            "Validation evidence remains insufficient or absent.",
        ),
        enablement_criteria=(
            "not_alpha_claim remains true",
            "paper_activation_allowed remains false",
            "shadow_activation_allowed remains false",
            "live_activation_allowed remains false",
        ),
    )


def map_grid_row_to_execution(row: dict[str, Any]) -> GridExecutionMapping:
    validation_campaign_id, run_label, output_subdir = _deterministic_ids(
        {
            **row,
            "sequence_number": int(row.get("sequence_number") or 0),
            "instrument_symbol": str(row.get("instrument_symbol") or "unknown"),
            "behavior_preset_id": str(row.get("behavior_preset_id") or "unknown"),
        }
    )
    safety_flags = _safety_flags(row)
    missing = _missing_required_fields(row)
    if missing:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_MISSING_METADATA,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=None,
            asset_symbol=str(row.get("instrument_symbol") or ""),
            timeframe=str(row.get("timeframe") or "") or None,
            hypothesis_id=str(row.get("hypothesis_id") or "") or None,
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=tuple(f"missing_{field}" for field in missing),
            preset_override=None,
        )
    if (
        not safety_flags["not_alpha_claim"]
        or safety_flags["paper_activation_allowed"]
        or safety_flags["shadow_activation_allowed"]
        or safety_flags["live_activation_allowed"]
    ):
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_SAFETY_VIOLATION,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=None,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("grid_row_failed_safety_invariants",),
            preset_override=None,
        )

    behavior_preset_id = str(row["behavior_preset_id"])
    template = _EXECUTION_TEMPLATES.get(behavior_preset_id)
    if template is None:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_UNSUPPORTED_MAPPING,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=None,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("unknown_behavior_preset_id",),
            preset_override=None,
        )

    asset_class = str(row["asset_class"])
    region = str(row["region"])
    if asset_class not in template.supported_asset_classes:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_ASSET_CLASS_MISMATCH,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=template.preset_reference,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("asset_class_not_supported_by_executable_mapping",),
            preset_override=None,
        )
    if region not in template.supported_regions:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_REGION_MISMATCH,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=template.preset_reference,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("region_not_supported_by_executable_mapping",),
            preset_override=None,
        )
    if not template.executable or template.preset_reference is None:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=template.unsupported_reason or BLOCKER_UNSUPPORTED_MAPPING,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=template.preset_reference,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("no_existing_executable_preset_for_behavior_family",),
            preset_override=None,
        )

    preset_override = _preset_override_for(row=row, template=template)
    catalog_preset = _CATALOG_PRESET_BY_ID.get(behavior_preset_id) or {}
    notes = [
        f"mapped_from_catalog_preset={behavior_preset_id}",
        f"strategy_or_preset_reference={template.preset_reference}",
    ]
    if catalog_preset:
        notes.append(
            f"catalog_required_data_quality={catalog_preset.get('required_data_quality')}"
        )
    return GridExecutionMapping(
        status="ready",
        blocker_class=None,
        validation_campaign_id=validation_campaign_id,
        strategy_or_preset_reference=template.preset_reference,
        asset_symbol=str(row["instrument_symbol"]),
        timeframe=str(row["timeframe"]),
        hypothesis_id=str(row["hypothesis_id"]),
        run_label=run_label,
        output_subdir=output_subdir,
        safety_flags=safety_flags,
        mapping_notes=tuple(notes),
        preset_override=preset_override,
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso_utc(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _latest_artifact_snapshot() -> dict[str, dict[str, Any] | None]:
    return {
        "run_manifest": _read_json(Path("research/run_manifest_latest.v1.json")),
        "run_meta": _read_json(Path("research/run_meta_latest.v1.json")),
        "screening_evidence": _read_json(Path("research/screening_evidence_latest.v1.json")),
        "run_candidates": _read_json(Path("research/run_candidates_latest.v1.json")),
        "run_campaign": _read_json(Path("research/run_campaign_latest.v1.json")),
    }


def _matching_screening_rows(
    screening_payload: dict[str, Any] | None,
    *,
    asset_symbol: str,
) -> list[dict[str, Any]]:
    candidates = screening_payload.get("candidates") if isinstance(screening_payload, dict) else []
    if not isinstance(candidates, list):
        return []
    return [
        row
        for row in candidates
        if isinstance(row, dict) and str(row.get("asset") or "") == asset_symbol
    ]


def _stage_rank(row: dict[str, Any]) -> tuple[int, int, float]:
    stage_result = str(row.get("stage_result") or "")
    near_pass = bool((row.get("near_pass") or {}).get("is_near_pass"))
    validation = row.get("validation_evidence") or {}
    metrics = row.get("metrics") or {}
    rank = {
        "promotion_candidate": 6,
        "needs_investigation": 5,
        "near_pass": 4,
        "screening_pass": 3,
        "screening_reject": 2,
        "unknown": 1,
    }.get(stage_result, 0)
    oos = int(validation.get("oos_trade_count") or 0)
    trades = float(metrics.get("totaal_trades", 0.0) or 0.0)
    return rank, 1 if near_pass else 0, oos + trades


def _best_screening_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=_stage_rank)


def _criteria_status(best_row: dict[str, Any] | None) -> str | None:
    if not best_row:
        return None
    blocked = list((best_row.get("promotion_guard") or {}).get("blocked_by") or [])
    if blocked:
        return ",".join(sorted(str(item) for item in blocked))
    if (best_row.get("promotion_guard") or {}).get("promotion_allowed") is True:
        return "promotion_allowed"
    failed = list((best_row.get("criteria") or {}).get("failed") or [])
    if failed:
        return ",".join(sorted(str(item) for item in failed))
    passed = list((best_row.get("criteria") or {}).get("passed") or [])
    if passed:
        return "criteria_passed_without_promotion"
    return None


def _derive_blocker(best_row: dict[str, Any] | None) -> str | None:
    if not best_row:
        return "missing_data"
    failure_reasons = [str(item) for item in list(best_row.get("failure_reasons") or [])]
    if "insufficient_trades" in failure_reasons:
        return "insufficient_trades"
    validation = best_row.get("validation_evidence") or {}
    validation_status = str(validation.get("status") or "")
    if validation_status == "no_oos_trades":
        return "no_oos_evidence"
    if validation_status == "insufficient_oos_trades":
        return "insufficient_trades"
    blocked = list((best_row.get("promotion_guard") or {}).get("blocked_by") or [])
    if blocked:
        return str(sorted(str(item) for item in blocked)[0])
    return None


def _derive_outcome(best_row: dict[str, Any] | None) -> str:
    if not best_row:
        return "unknown"
    if (best_row.get("promotion_guard") or {}).get("promotion_allowed") is True:
        return "promotion_candidate"
    if bool((best_row.get("near_pass") or {}).get("is_near_pass")):
        return "near_pass"
    validation = best_row.get("validation_evidence") or {}
    status = str(validation.get("status") or "")
    if status == "sufficient_oos_evidence":
        return "sufficient_oos_evidence"
    if status == "no_oos_trades":
        return "screening_pass_no_oos"
    return str(best_row.get("stage_result") or "unknown")


def _run_existing_research_path(mapping: GridExecutionMapping) -> None:
    run_research_module = importlib.import_module("research.run_research")
    run_research_module.run_research(preset_override=mapping.preset_override)


def _write_execution_summary_sidecar(
    *,
    row: dict[str, Any],
    mapping: GridExecutionMapping,
    observation: GridExecutionObservation,
    output_dir: Path,
    artifacts: dict[str, dict[str, Any] | None],
    matching_rows: list[dict[str, Any]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "execution_result.v1.json"
    payload = {
        "report_kind": RESULT_REPORT_KIND,
        "grid_row": {
            "sequence_number": row["sequence_number"],
            "instrument_symbol": row["instrument_symbol"],
            "behavior_preset_id": row["behavior_preset_id"],
            "hypothesis_id": row["hypothesis_id"],
            "timeframe": row["timeframe"],
            "region": row["region"],
            "asset_class": row["asset_class"],
        },
        "mapping": mapping.to_payload(),
        "observation": {
            "status": observation.status,
            "outcome_class": observation.outcome_class,
            "blocker_class": observation.blocker_class,
            "error_class": observation.error_class,
            "trades_total": observation.trades_total,
            "oos_trades": observation.oos_trades,
            "hd_trades": observation.hd_trades,
            "criteria_status": observation.criteria_status,
            "promotion_candidate": observation.promotion_candidate,
            "near_pass": observation.near_pass,
            "safe_to_promote": observation.safe_to_promote,
            "candidate_count": observation.candidate_count,
            "started_at_utc": observation.started_at_utc,
            "finished_at_utc": observation.finished_at_utc,
            "duration_seconds": observation.duration_seconds,
            "execution_notes": list(observation.execution_notes),
        },
        "artifact_snapshot": {
            "run_manifest": artifacts["run_manifest"],
            "run_meta": artifacts["run_meta"],
            "run_campaign": artifacts["run_campaign"],
            "matching_screening_rows": matching_rows,
        },
    }
    summary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "execution_result": summary_path.as_posix(),
        "run_manifest_latest": "research/run_manifest_latest.v1.json",
        "run_meta_latest": "research/run_meta_latest.v1.json",
        "screening_evidence_latest": "research/screening_evidence_latest.v1.json",
        "run_candidates_latest": "research/run_candidates_latest.v1.json",
        "run_campaign_latest": "research/run_campaign_latest.v1.json",
    }


def _skipped_observation(
    *,
    blocker_class: str,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    notes: tuple[str, ...],
) -> GridExecutionObservation:
    return GridExecutionObservation(
        status="skipped",
        outcome_class="skipped",
        blocker_class=blocker_class,
        error_class=None,
        trades_total=None,
        oos_trades=None,
        hd_trades=None,
        criteria_status=None,
        promotion_candidate=False,
        near_pass=False,
        safe_to_promote=False,
        artifact_paths={},
        candidate_count=0,
        started_at_utc=_iso_utc(started_at),
        finished_at_utc=_iso_utc(finished_at),
        duration_seconds=max((finished_at - started_at).total_seconds(), 0.0),
        execution_notes=notes,
    )


def execute_grid_row(
    row: dict[str, Any],
    *,
    output_dir: Path,
    execution_runner: Any | None = None,
) -> dict[str, Any]:
    started_at = _utcnow()
    mapping = map_grid_row_to_execution(row)
    if mapping.status != "ready":
        finished_at = _utcnow()
        observation = _skipped_observation(
            blocker_class=str(mapping.blocker_class),
            started_at=started_at,
            finished_at=finished_at,
            notes=mapping.mapping_notes,
        )
        artifact_paths = _write_execution_summary_sidecar(
            row=row,
            mapping=mapping,
            observation=observation,
            output_dir=output_dir,
            artifacts=_latest_artifact_snapshot(),
            matching_rows=[],
        )
        return {
            **row,
            "status": observation.status,
            "outcome_class": observation.outcome_class,
            "blocker_class": observation.blocker_class,
            "error_class": observation.error_class,
            "trades_total": observation.trades_total,
            "oos_trades": observation.oos_trades,
            "hd_trades": observation.hd_trades,
            "criteria_status": observation.criteria_status,
            "promotion_candidate": observation.promotion_candidate,
            "near_pass": observation.near_pass,
            "safe_to_promote": observation.safe_to_promote,
            "artifact_paths": artifact_paths,
            "result_path": artifact_paths["execution_result"],
            "validation_campaign_id": mapping.validation_campaign_id,
            "strategy_or_preset_reference": mapping.strategy_or_preset_reference,
            "run_label": mapping.run_label,
            "output_subdir": mapping.output_subdir,
            "started_at_utc": observation.started_at_utc,
            "finished_at_utc": observation.finished_at_utc,
            "duration_seconds": observation.duration_seconds,
            "execution_notes": list(observation.execution_notes),
        }

    runner = execution_runner or _run_existing_research_path
    try:
        runner(mapping)
        status = "completed"
        error_class = None
        blocker_class = None
        execution_notes = ("existing_run_research_path_executed",)
    except Exception as exc:  # pragma: no cover - exercised via tests with stubs
        degenerate = type(exc).__name__ == "DegenerateResearchRunError"
        status = "completed" if degenerate else "failed"
        error_class = type(exc).__name__
        blocker_class = (
            "degenerate_no_survivors" if degenerate else BLOCKER_CONTROLLED_VALIDATION_FAILED
        )
        execution_notes = (
            "existing_run_research_path_executed",
            "exception_raised_during_execution",
        )

    finished_at = _utcnow()
    artifacts = _latest_artifact_snapshot()
    matching_rows = _matching_screening_rows(
        artifacts["screening_evidence"],
        asset_symbol=str(row["instrument_symbol"]),
    )
    best_row = _best_screening_row(matching_rows)
    trades_total = (
        float((best_row.get("metrics") or {}).get("totaal_trades", 0.0) or 0.0)
        if best_row is not None
        else None
    )
    oos_trades = (
        int((best_row.get("validation_evidence") or {}).get("oos_trade_count") or 0)
        if best_row is not None
        else None
    )
    hd_trades = (
        max(trades_total - float(oos_trades or 0), 0.0)
        if trades_total is not None and oos_trades is not None
        else None
    )
    promotion_candidate = bool(
        best_row is not None
        and (
            (best_row.get("promotion_guard") or {}).get("promotion_allowed") is True
            or str(best_row.get("stage_result") or "") == "promotion_candidate"
        )
    )
    near_pass = bool(
        best_row is not None and bool((best_row.get("near_pass") or {}).get("is_near_pass"))
    )
    observation = GridExecutionObservation(
        status=status,
        outcome_class=_derive_outcome(best_row),
        blocker_class=blocker_class or _derive_blocker(best_row),
        error_class=error_class if status == "failed" else None,
        trades_total=trades_total,
        oos_trades=oos_trades,
        hd_trades=hd_trades,
        criteria_status=_criteria_status(best_row),
        promotion_candidate=promotion_candidate,
        near_pass=near_pass,
        safe_to_promote=promotion_candidate,
        artifact_paths={},
        candidate_count=len(matching_rows),
        started_at_utc=_iso_utc(started_at),
        finished_at_utc=_iso_utc(finished_at),
        duration_seconds=max((finished_at - started_at).total_seconds(), 0.0),
        execution_notes=execution_notes,
    )
    artifact_paths = _write_execution_summary_sidecar(
        row=row,
        mapping=mapping,
        observation=observation,
        output_dir=output_dir,
        artifacts=artifacts,
        matching_rows=matching_rows,
    )
    return {
        **row,
        "status": observation.status,
        "outcome_class": observation.outcome_class,
        "blocker_class": observation.blocker_class,
        "error_class": observation.error_class,
        "trades_total": observation.trades_total,
        "oos_trades": observation.oos_trades,
        "hd_trades": observation.hd_trades,
        "criteria_status": observation.criteria_status,
        "promotion_candidate": observation.promotion_candidate,
        "near_pass": observation.near_pass,
        "safe_to_promote": observation.safe_to_promote,
        "artifact_paths": artifact_paths,
        "result_path": artifact_paths["execution_result"],
        "validation_campaign_id": mapping.validation_campaign_id,
        "strategy_or_preset_reference": mapping.strategy_or_preset_reference,
        "run_label": mapping.run_label,
        "output_subdir": mapping.output_subdir,
        "started_at_utc": observation.started_at_utc,
        "finished_at_utc": observation.finished_at_utc,
        "duration_seconds": observation.duration_seconds,
        "execution_notes": list(observation.execution_notes),
    }
