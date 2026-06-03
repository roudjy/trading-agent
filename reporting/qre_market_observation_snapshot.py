"""Read-only QRE market observation snapshot projector.

This module projects local research artifacts into durable market observations.
It is intentionally non-executing: it does not run research, launch tools,
mutate strategies or presets, write queues, or activate runtime paths.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_market_observation_snapshot"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_market_observations"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_market_observations/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DEFAULT_SOURCE_CANDIDATES: Final[tuple[Path, ...]] = (
    REPO_ROOT / "research" / "screening_evidence_latest.v1.json",
    REPO_ROOT / "research" / "run_candidates_latest.v1.json",
    REPO_ROOT / "research" / "research_latest.json",
)

OBSERVATION_TYPES: Final[tuple[str, ...]] = (
    "exit_failure_pattern",
    "low_trade_count",
    "high_window_end_impact",
    "source_quality_issue",
    "paper_divergence",
    "unknown",
)

OPTIONAL_EXECUTABLE_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "executable_hypothesis_id",
    "source_hypothesis_id",
    "strategy_family",
    "strategy_template_id",
    "preset_name",
    "candidate_id",
    "strategy_id",
)

NOTE_INPUT_ABSENT: Final[str] = "market_source_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "market_source_artifact_unparseable"
NOTE_NO_OBSERVATIONS: Final[str] = "no_market_observations_projected"
NOTE_OBSERVATIONS_PRESENT: Final[str] = "market_observations_present"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> tuple[bool, dict[str, Any] | None]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return (False, None)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return (True, None)
    return (True, parsed if isinstance(parsed, dict) else None)


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _bounded_identity_str(value: Any, *, max_len: int = 160) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if not isinstance(value, str | int | float):
        return ""
    return _bounded_str(value, max_len=max_len)


def _explicit_identity_fields(raw: dict[str, Any]) -> dict[str, str]:
    return {
        field: value
        for field in OPTIONAL_EXECUTABLE_IDENTITY_FIELDS
        if (value := _bounded_identity_str(raw.get(field)))
    }


def _str_list(value: Any, *, max_items: int = 12, max_len: int = 120) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in raw_items[:max_items]:
        text = _bounded_str(item, max_len=max_len)
        if text:
            out.append(text)
    return out


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_true(value: Any) -> bool:
    return value is True


def _observation_id(
    *,
    source_artifact: str,
    observation_type: str,
    asset_scope: list[str],
    timeframe_scope: list[str],
    summary: str,
) -> str:
    seed = "|".join(
        [
            source_artifact,
            observation_type,
            ",".join(asset_scope),
            ",".join(timeframe_scope),
            summary,
        ]
    )
    return "qre-obs-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _normalise_fixture_observation(
    raw: dict[str, Any],
    *,
    source_artifact: str,
) -> dict[str, Any]:
    observation_type = _bounded_str(raw.get("observation_type"), max_len=80)
    if observation_type not in OBSERVATION_TYPES:
        observation_type = "unknown"
    asset_scope = _str_list(raw.get("asset_scope")) or ["unknown"]
    timeframe_scope = _str_list(raw.get("timeframe_scope")) or ["unknown"]
    summary = _bounded_str(raw.get("summary"), max_len=360) or "Unspecified observation."
    observation_id = _bounded_str(raw.get("observation_id"), max_len=120)
    if not observation_id:
        observation_id = _observation_id(
            source_artifact=source_artifact,
            observation_type=observation_type,
            asset_scope=asset_scope,
            timeframe_scope=timeframe_scope,
            summary=summary,
        )

    confidence = _float_or_none(raw.get("confidence"))
    if confidence is None:
        confidence = 0.5

    return {
        "observation_id": observation_id,
        "source_artifact": source_artifact,
        "observation_type": observation_type,
        "asset_scope": asset_scope,
        "timeframe_scope": timeframe_scope,
        "regime_tags": _str_list(raw.get("regime_tags"), max_items=16),
        "metric_refs": _str_list(raw.get("metric_refs"), max_items=24, max_len=180),
        "summary": summary,
        "confidence": max(0.0, min(1.0, confidence)),
        "supporting_evidence_refs": _str_list(
            raw.get("supporting_evidence_refs"), max_items=24, max_len=180
        ),
        "contradicting_evidence_refs": _str_list(
            raw.get("contradicting_evidence_refs"), max_items=24, max_len=180
        ),
        "safe_to_execute": False,
        **_explicit_identity_fields(raw),
    }


def _metric_ref(name: str, value: Any) -> str:
    return f"{name}:{_bounded_str(value, max_len=80)}"


def _row_identity(row: dict[str, Any]) -> str:
    strategy = (
        _bounded_str(row.get("strategy_id"), max_len=80)
        or _bounded_str(row.get("strategy_name"), max_len=80)
        or "unknown_strategy"
    )
    asset = _bounded_str(row.get("asset"), max_len=80) or "unknown_asset"
    interval = _bounded_str(row.get("interval"), max_len=40) or "unknown_timeframe"
    return f"{strategy}|{asset}|{interval}"


def _source_has_explicit_executable_identity(payload: dict[str, Any]) -> bool:
    for field in ("results", "candidates", "observations"):
        rows = payload.get(field)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and _bounded_identity_str(row.get("executable_hypothesis_id")):
                return True
    return False


def _metric_refs_from_row(raw: dict[str, Any]) -> list[str]:
    metrics = raw.get("metrics")
    if not isinstance(metrics, dict):
        metrics = raw.get("diagnostic_metrics")
    metric_source = metrics if isinstance(metrics, dict) else raw
    refs = [
        _metric_ref("win_rate", metric_source.get("win_rate")),
        _metric_ref("sharpe", metric_source.get("sharpe")),
        _metric_ref("deflated_sharpe", metric_source.get("deflated_sharpe")),
        _metric_ref("trades_per_month", metric_source.get("trades_per_maand")),
        _metric_ref("total_trades", metric_source.get("totaal_trades")),
        _metric_ref("expectancy", metric_source.get("expectancy")),
        _metric_ref("profit_factor", metric_source.get("profit_factor")),
        _metric_ref("max_drawdown", metric_source.get("max_drawdown")),
    ]
    return [ref for ref in refs if not ref.endswith(":")]


def _candidate_summary(row_ref: str, raw: dict[str, Any]) -> str:
    status = (
        _bounded_str(raw.get("qre_validation_linkage_status"), max_len=120)
        or _bounded_str(raw.get("stage_result"), max_len=120)
        or _bounded_str(raw.get("current_status"), max_len=120)
        or "candidate_context_available"
    )
    return f"Candidate source row {row_ref} exposes explicit validation context: {status}."


def _build_candidate_observations(
    payload: dict[str, Any],
    *,
    source_artifact: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        return ([], [NOTE_INPUT_UNPARSEABLE])

    observations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw in enumerate(raw_candidates, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"candidate_{index}:not_object")
            continue

        asset_scope = [_bounded_str(raw.get("asset"), max_len=80) or "unknown"]
        timeframe_scope = [_bounded_str(raw.get("interval"), max_len=40) or "unknown"]
        strategy_family = _bounded_str(raw.get("strategy_family"), max_len=80)
        regime_tags = [strategy_family] if strategy_family else []
        row_ref = _bounded_str(raw.get("candidate_id"), max_len=160) or _row_identity(raw)
        identity_fields = _explicit_identity_fields(raw)
        summary = _candidate_summary(row_ref, raw)
        observation_id = _observation_id(
            source_artifact=source_artifact,
            observation_type="unknown",
            asset_scope=asset_scope,
            timeframe_scope=timeframe_scope,
            summary=summary,
        )
        observations.append(
            {
                "observation_id": observation_id,
                "source_artifact": source_artifact,
                "observation_type": "unknown",
                "asset_scope": asset_scope,
                "timeframe_scope": timeframe_scope,
                "regime_tags": regime_tags,
                "metric_refs": _metric_refs_from_row(raw),
                "summary": summary,
                "confidence": 0.5,
                "supporting_evidence_refs": [f"{source_artifact}#{row_ref}"],
                "contradicting_evidence_refs": [],
                "safe_to_execute": False,
                **identity_fields,
            }
        )

    observations.sort(key=lambda item: item["observation_id"])
    return (observations, warnings)


def _build_research_observations(
    payload: dict[str, Any],
    *,
    source_artifact: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return ([], [NOTE_INPUT_UNPARSEABLE])

    observations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw in enumerate(raw_results, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"result_{index}:not_object")
            continue

        asset_scope = [_bounded_str(raw.get("asset"), max_len=80) or "unknown"]
        timeframe_scope = [_bounded_str(raw.get("interval"), max_len=40) or "unknown"]
        family = _bounded_str(raw.get("family"), max_len=80)
        regime_tags = [family] if family else []
        row_ref = _row_identity(raw)
        identity_fields = _explicit_identity_fields(raw)
        metric_refs = [
            _metric_ref("win_rate", raw.get("win_rate")),
            _metric_ref("sharpe", raw.get("sharpe")),
            _metric_ref("deflated_sharpe", raw.get("deflated_sharpe")),
            _metric_ref("trades_per_month", raw.get("trades_per_maand")),
            _metric_ref("total_trades", raw.get("totaal_trades")),
            _metric_ref("consistency", raw.get("consistentie")),
        ]
        supporting_refs = [f"{source_artifact}#{row_ref}"]
        contradicting_refs: list[str] = []

        success = raw.get("success")
        error = _bounded_str(raw.get("error"), max_len=160)
        total_trades = _float_or_none(raw.get("totaal_trades"))
        trades_per_month = _float_or_none(raw.get("trades_per_maand"))
        sharpe = _float_or_none(raw.get("sharpe"))
        consistency = _float_or_none(raw.get("consistentie"))

        projected: list[tuple[str, str, float]] = []
        if success is False or error:
            projected.append(
                (
                    "source_quality_issue",
                    f"Research row {row_ref} reports a failed or error-bearing source result.",
                    0.85,
                )
            )
        if (total_trades is not None and total_trades < 30) or (
            trades_per_month is not None and trades_per_month < 1.0
        ):
            projected.append(
                (
                    "low_trade_count",
                    f"Research row {row_ref} has limited sample support for validation.",
                    0.8,
                )
            )
        if (consistency is not None and consistency == 0.0) and (
            total_trades is not None and total_trades < 40
        ):
            projected.append(
                (
                    "high_window_end_impact",
                    f"Research row {row_ref} may be sensitive to fold or window boundaries.",
                    0.65,
                )
            )
        if "tp_sl" in _bounded_str(raw.get("strategy_name"), max_len=120) and (
            sharpe is not None and sharpe < 0.0
        ):
            projected.append(
                (
                    "exit_failure_pattern",
                    f"Research row {row_ref} suggests exit management may be degrading edge.",
                    0.7,
                )
            )
        if _bool_true(raw.get("paper_divergence")) or _bool_true(
            raw.get("paper_engine_divergence")
        ):
            projected.append(
                (
                    "paper_divergence",
                    f"Research row {row_ref} indicates a paper or engine parity divergence.",
                    0.9,
                )
            )
        if not projected and raw_results:
            projected.append(
                (
                    "unknown",
                    f"Research row {row_ref} has no specific closed-loop observation rule.",
                    0.4,
                )
            )

        for observation_type, summary, confidence in projected:
            observation_id = _observation_id(
                source_artifact=source_artifact,
                observation_type=observation_type,
                asset_scope=asset_scope,
                timeframe_scope=timeframe_scope,
                summary=summary,
            )
            observations.append(
                {
                    "observation_id": observation_id,
                    "source_artifact": source_artifact,
                    "observation_type": observation_type,
                    "asset_scope": asset_scope,
                    "timeframe_scope": timeframe_scope,
                    "regime_tags": regime_tags,
                    "metric_refs": metric_refs,
                    "summary": summary,
                    "confidence": confidence,
                    "supporting_evidence_refs": supporting_refs,
                    "contradicting_evidence_refs": contradicting_refs,
                    "safe_to_execute": False,
                    **identity_fields,
                }
            )

    observations.sort(key=lambda item: item["observation_id"])
    return (observations, warnings)


def _select_default_source() -> Path:
    for path in DEFAULT_SOURCE_CANDIDATES:
        available, payload = _read_json(path)
        if (
            available
            and isinstance(payload, dict)
            and _source_has_explicit_executable_identity(payload)
        ):
            return path
    return REPO_ROOT / "research" / "research_latest.json"


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_observation_type": {kind: 0 for kind in OBSERVATION_TYPES},
    }


def _counts(observations: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(item.get("observation_type") or "unknown") for item in observations)
    out = _empty_counts()
    out["total"] = len(observations)
    for kind in OBSERVATION_TYPES:
        out["by_observation_type"][kind] = counter.get(kind, 0)
    return out


def _final_recommendation(observations: list[dict[str, Any]]) -> str:
    if observations:
        return "market_observations_ready_for_hypothesis_projection"
    return "no_market_observations_available"


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    observations: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "supported_observation_types": list(OBSERVATION_TYPES),
        "observations": observations,
        "counts": _counts(observations),
        "validation_warnings": validation_warnings,
        "final_recommendation": _final_recommendation(observations),
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "eligible_for_direct_execution": False,
    }


def collect_snapshot(
    *,
    source_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = source_path or _select_default_source()
    available, payload = _read_json(source)
    if payload is None:
        note = NOTE_INPUT_UNPARSEABLE if available else NOTE_INPUT_ABSENT
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=available,
            note=note,
            observations=[],
            validation_warnings=[note],
        )

    source_artifact = _rel(source)
    if "observations" in payload:
        raw_observations = payload.get("observations")
        if not isinstance(raw_observations, list) or not all(
            isinstance(item, dict) for item in raw_observations
        ):
            return _base_snapshot(
                generated_at_utc=generated,
                input_artifact_path=source,
                input_artifact_available=True,
                note=NOTE_INPUT_UNPARSEABLE,
                observations=[],
                validation_warnings=[NOTE_INPUT_UNPARSEABLE],
            )
        observations = [
            _normalise_fixture_observation(item, source_artifact=source_artifact)
            for item in raw_observations
        ]
        observations.sort(key=lambda item: item["observation_id"])
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_OBSERVATIONS_PRESENT if observations else NOTE_NO_OBSERVATIONS,
            observations=observations,
            validation_warnings=[],
        )

    if "candidates" in payload:
        observations, warnings = _build_candidate_observations(
            payload,
            source_artifact=source_artifact,
        )
        if NOTE_INPUT_UNPARSEABLE in warnings:
            return _base_snapshot(
                generated_at_utc=generated,
                input_artifact_path=source,
                input_artifact_available=True,
                note=NOTE_INPUT_UNPARSEABLE,
                observations=[],
                validation_warnings=warnings,
            )
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_OBSERVATIONS_PRESENT if observations else NOTE_NO_OBSERVATIONS,
            observations=observations,
            validation_warnings=warnings,
        )

    observations, warnings = _build_research_observations(
        payload,
        source_artifact=source_artifact,
    )
    if NOTE_INPUT_UNPARSEABLE in warnings:
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            observations=[],
            validation_warnings=warnings,
        )

    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_OBSERVATIONS_PRESENT if observations else NOTE_NO_OBSERVATIONS,
        observations=observations,
        validation_warnings=warnings,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE market observation dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_market_observations.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_market_observation_snapshot",
        description="Project local research artifacts into read-only QRE observations.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        source_path=args.source,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "DEFAULT_SOURCE_CANDIDATES",
    "OPTIONAL_EXECUTABLE_IDENTITY_FIELDS",
    "OBSERVATION_TYPES",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
