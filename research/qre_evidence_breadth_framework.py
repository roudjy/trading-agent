from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import production_discovery_catalog as discovery_catalog
from research.equity_universe_catalog import build_equity_universe_catalog
from research.qre_real_basket_evidence_coverage import build_real_basket_evidence_coverage


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_evidence_breadth_framework"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_evidence_breadth_framework")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_evidence_breadth_framework/"
DEFAULT_DISPOSITION_MEMORY_PATH: Final[Path] = Path("logs/qre_hypothesis_disposition_memory/latest.json")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _disposition_record(repo_root: Path, disposition_memory_path: Path) -> dict[str, Any]:
    payload = _read_json(repo_root / disposition_memory_path)
    record = payload.get("record") if isinstance(payload, Mapping) and isinstance(payload.get("record"), Mapping) else {}
    return dict(record)


def _discovery_assets() -> list[dict[str, Any]]:
    return [asset.to_payload() for asset in discovery_catalog.list_assets()]


def _discovery_presets() -> list[dict[str, Any]]:
    return [preset.to_payload() for preset in discovery_catalog.list_presets()]


def _coverage_rows(repo_root: Path, max_candidates: int) -> list[dict[str, Any]]:
    report = build_real_basket_evidence_coverage(repo_root=repo_root, max_candidates=max_candidates)
    rows = report.get("rows")
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def _filter_non_crypto_assets(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if _text(row.get("asset_class")).lower() != "crypto"
    ]


def _accepted_symbols_from_disposition(record: Mapping[str, Any]) -> list[str]:
    symbols = record.get("symbols")
    if isinstance(symbols, Sequence) and not isinstance(symbols, (str, bytes)):
        return _unique_in_order(symbols)
    return []


def _group_values_for_universe(instruments: Sequence[Mapping[str, Any]], universe_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in instruments
        if universe_id in {str(value) for value in row.get("universe_ids", [])}
    ]


def _match_coverage_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    dimension: str,
    scope_key: str,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in rows:
        if dimension == "symbol" and _text(row.get("symbol")) == scope_key:
            matched.append(dict(row))
        elif dimension == "basket" and _text(row.get("candidate_id")) == scope_key:
            matched.append(dict(row))
        elif dimension == "region" and _text(row.get("region")) == scope_key:
            matched.append(dict(row))
        elif dimension == "sector":
            symbol = _text(row.get("symbol"))
            if symbol and scope_key == _text(row.get("_sector_lookup")):
                matched.append(dict(row))
        elif dimension == "behavior" and _text(row.get("behavior_family")) == scope_key:
            matched.append(dict(row))
        elif dimension == "preset" and _text(row.get("preset_id")) == scope_key:
            matched.append(dict(row))
        elif dimension == "timeframe" and scope_key in {str(value) for value in row.get("timeframes", [])}:
            matched.append(dict(row))
    return matched


def _coverage_counters(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(_text(row.get("evidence_completeness_status")) or "unknown" for row in rows)
    return dict(sorted(counter.items()))


def _blocked_reasons(rows: Sequence[Mapping[str, Any]], *, default_reason: str) -> list[str]:
    reasons = [
        reason
        for row in rows
        for reason in row.get("missing_evidence_taxonomy", [])
        if _text(reason)
    ]
    if reasons:
        return _unique_in_order(reasons)
    return [default_reason]


def _rejected_scope_match(record: Mapping[str, Any], *, dimension: str, scope_key: str) -> bool:
    disposition_scope = record.get("disposition_scope") if isinstance(record.get("disposition_scope"), Mapping) else {}
    if dimension == "behavior":
        return _text(record.get("behavior_id")) == scope_key or _text(disposition_scope.get("behavior_id")) == scope_key
    if dimension == "preset":
        return _text(record.get("preset_id")) == scope_key or _text(disposition_scope.get("preset_id")) == scope_key
    if dimension == "timeframe":
        return _text(record.get("timeframe")) == scope_key or _text(disposition_scope.get("timeframe")) == scope_key
    if dimension == "regime":
        return scope_key in {str(value) for value in record.get("regime_refs", [])}
    if dimension == "independent_oos_window":
        return scope_key in {str(value) for value in record.get("window_refs", [])}
    if dimension == "symbol":
        return scope_key in set(_accepted_symbols_from_disposition(record))
    return False


def _accepted_counts(
    record: Mapping[str, Any],
    *,
    dimension: str,
    scope_key: str,
) -> tuple[int, int]:
    lineage_count = len(record.get("accepted_lineage_refs") or [])
    oos_count = len(record.get("accepted_oos_refs") or [])
    if _rejected_scope_match(record, dimension=dimension, scope_key=scope_key):
        return lineage_count, oos_count
    return 0, 0


def _reproducibility_status(rows: Sequence[Mapping[str, Any]], accepted_oos_count: int) -> str:
    if not rows:
        return "blocked_no_inventory"
    if any(int(row.get("evidence_completeness_score_pct") or 0) >= 85 for row in rows) and accepted_oos_count > 0:
        return "reproducible_authoritative"
    if any(int(row.get("evidence_completeness_score_pct") or 0) > 0 for row in rows):
        return "working_read_only"
    return "context_only"


def _breadth_priority(
    *,
    dimension: str,
    inventory_count: int,
    basket_count: int,
    accepted_oos_count: int,
    incomplete_hypothesis_count: int,
) -> int:
    base = 0
    if inventory_count > 0:
        base += 40
    if basket_count > 0:
        base += 20
    if accepted_oos_count == 0:
        base += 25
    if incomplete_hypothesis_count > 0:
        base += 10
    if dimension in {"region", "behavior", "preset", "timeframe"}:
        base += 5
    return base


def _matrix_row(
    *,
    dimension: str,
    scope_key: str,
    label: str,
    inventory_count: int,
    coverage_rows: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any],
) -> dict[str, Any]:
    accepted_lineage_count, accepted_oos_count = _accepted_counts(record, dimension=dimension, scope_key=scope_key)
    rejected_hypothesis_count = 1 if _rejected_scope_match(record, dimension=dimension, scope_key=scope_key) else 0
    unique_hypotheses = {_text(row.get("hypothesis_id")) for row in coverage_rows if _text(row.get("hypothesis_id"))}
    supported_hypothesis_count = 1 if accepted_oos_count > 0 and rejected_hypothesis_count == 0 else 0
    incomplete_hypothesis_count = max(0, len(unique_hypotheses) - supported_hypothesis_count - rejected_hypothesis_count)
    counters = _coverage_counters(coverage_rows)
    blocker_reasons = _blocked_reasons(
        coverage_rows,
        default_reason="no_discovery_basket_inventory_for_scope" if inventory_count > 0 else "no_configured_inventory_for_scope",
    )
    return {
        "dimension": dimension,
        "scope_key": scope_key,
        "scope_label": label,
        "inventory_count": inventory_count,
        "basket_count": len(coverage_rows),
        "coverage_status_counts": counters,
        "accepted_lineage_count": accepted_lineage_count,
        "accepted_oos_count": accepted_oos_count,
        "supported_hypothesis_count": supported_hypothesis_count,
        "rejected_hypothesis_count": rejected_hypothesis_count,
        "incomplete_hypothesis_count": incomplete_hypothesis_count,
        "independent_window_count": len(record.get("window_refs") or []) if dimension in {"regime", "independent_oos_window"} else 0,
        "regime_count": len(record.get("regime_refs") or []) if dimension in {"regime", "independent_oos_window"} else 0,
        "reproducibility_status": _reproducibility_status(coverage_rows, accepted_oos_count),
        "blocker_reasons": blocker_reasons,
        "breadth_priority_score": _breadth_priority(
            dimension=dimension,
            inventory_count=inventory_count,
            basket_count=len(coverage_rows),
            accepted_oos_count=accepted_oos_count,
            incomplete_hypothesis_count=incomplete_hypothesis_count,
        ),
    }


def _recommendations(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    filtered = [
        dict(row)
        for row in rows
        if int(row.get("inventory_count") or 0) > 0 and int(row.get("accepted_oos_count") or 0) == 0
    ]
    filtered.sort(
        key=lambda row: (
            -int(row.get("breadth_priority_score") or 0),
            str(row.get("dimension") or ""),
            str(row.get("scope_key") or ""),
        )
    )
    recommendations: list[dict[str, Any]] = []
    for row in filtered[:12]:
        recommendations.append(
            {
                "dimension": row["dimension"],
                "scope_key": row["scope_key"],
                "scope_label": row["scope_label"],
                "priority_score": row["breadth_priority_score"],
                "reason": (
                    "Inventory exists, accepted OOS remains absent, and the current scope is still incomplete."
                ),
                "blocker_reasons": list(row.get("blocker_reasons") or []),
                "recommended_next_action": (
                    "plan_additional_independent_windows"
                    if row["dimension"] in {"regime", "independent_oos_window"}
                    else "plan_read_only_breadth_expansion"
                ),
            }
        )
    return recommendations


def build_evidence_breadth_framework(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
    requested_universe_ids: Sequence[str] | None = None,
    requested_regions: Sequence[str] | None = None,
    requested_behaviors: Sequence[str] | None = None,
    requested_timeframes: Sequence[str] | None = None,
    requested_sectors: Sequence[str] | None = None,
    disposition_memory_path: Path = DEFAULT_DISPOSITION_MEMORY_PATH,
) -> dict[str, Any]:
    universe_catalog = build_equity_universe_catalog()
    instruments = _filter_non_crypto_assets(universe_catalog.get("instruments", []))
    discovery_assets = _filter_non_crypto_assets(_discovery_assets())
    discovery_presets = _discovery_presets()
    coverage_rows = _coverage_rows(repo_root=repo_root, max_candidates=max_candidates)
    record = _disposition_record(repo_root, disposition_memory_path)

    sector_by_symbol = {_text(row.get("symbol")): _text(row.get("sector")) for row in discovery_assets}
    coverage_rows = [{**dict(row), "_sector_lookup": sector_by_symbol.get(_text(row.get("symbol")), "")} for row in coverage_rows]

    requested = {
        "universe_ids": _unique_in_order(requested_universe_ids or [str(row["universe_id"]) for row in universe_catalog.get("universes", [])]),
        "regions": _unique_in_order(requested_regions or sorted({_text(row.get("region")) for row in discovery_assets if _text(row.get("region"))})),
        "behaviors": _unique_in_order(requested_behaviors or sorted({_text(row.get("behavior_family")) for row in discovery_presets if _text(row.get("behavior_family"))})),
        "timeframes": _unique_in_order(requested_timeframes or sorted({value for row in discovery_presets for value in row.get("allowed_timeframes", []) if _text(value)})),
        "sectors": _unique_in_order(requested_sectors or sorted({_text(row.get("sector")) for row in discovery_assets if _text(row.get("sector")) and _text(row.get("asset_class")) == "equity"})),
    }

    matrix_rows: list[dict[str, Any]] = []

    symbols = sorted({_text(row.get("symbol")) for row in coverage_rows if _text(row.get("symbol"))})
    for symbol in symbols:
        inventory_count = sum(1 for row in discovery_assets if _text(row.get("symbol")) == symbol)
        matrix_rows.append(
            _matrix_row(
                dimension="symbol",
                scope_key=symbol,
                label=symbol,
                inventory_count=inventory_count,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="symbol", scope_key=symbol),
                record=record,
            )
        )

    for basket in discovery_catalog.build_bounded_candidate_basket(max_candidates=max_candidates):
        basket_id = _text(basket.get("candidate_id"))
        matrix_rows.append(
            _matrix_row(
                dimension="basket",
                scope_key=basket_id,
                label=basket_id,
                inventory_count=1,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="basket", scope_key=basket_id),
                record=record,
            )
        )

    for region in requested["regions"]:
        inventory_count = sum(1 for row in discovery_assets if _text(row.get("region")) == region)
        matrix_rows.append(
            _matrix_row(
                dimension="region",
                scope_key=region,
                label=region,
                inventory_count=inventory_count,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="region", scope_key=region),
                record=record,
            )
        )

    for sector in requested["sectors"]:
        inventory_count = sum(1 for row in discovery_assets if _text(row.get("sector")) == sector and _text(row.get("asset_class")) == "equity")
        matrix_rows.append(
            _matrix_row(
                dimension="sector",
                scope_key=sector,
                label=sector,
                inventory_count=inventory_count,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="sector", scope_key=sector),
                record=record,
            )
        )

    for universe_id in requested["universe_ids"]:
        inventory_count = len(_group_values_for_universe(instruments, universe_id))
        matching_symbols = {_text(row.get("symbol")) for row in _group_values_for_universe(instruments, universe_id)}
        matrix_rows.append(
            _matrix_row(
                dimension="universe",
                scope_key=universe_id,
                label=universe_id,
                inventory_count=inventory_count,
                coverage_rows=[dict(row) for row in coverage_rows if _text(row.get("symbol")) in matching_symbols],
                record=record,
            )
        )

    for behavior in requested["behaviors"]:
        inventory_count = sum(1 for row in discovery_presets if _text(row.get("behavior_family")) == behavior)
        matrix_rows.append(
            _matrix_row(
                dimension="behavior",
                scope_key=behavior,
                label=behavior,
                inventory_count=inventory_count,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="behavior", scope_key=behavior),
                record=record,
            )
        )

    for preset in sorted({_text(row.get("preset_id")) for row in discovery_presets if _text(row.get("preset_id"))}):
        inventory_count = 1
        matrix_rows.append(
            _matrix_row(
                dimension="preset",
                scope_key=preset,
                label=preset,
                inventory_count=inventory_count,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="preset", scope_key=preset),
                record=record,
            )
        )

    for timeframe in requested["timeframes"]:
        inventory_count = sum(1 for row in discovery_presets if timeframe in {str(value) for value in row.get("allowed_timeframes", [])})
        matrix_rows.append(
            _matrix_row(
                dimension="timeframe",
                scope_key=timeframe,
                label=timeframe,
                inventory_count=inventory_count,
                coverage_rows=_match_coverage_rows(coverage_rows, dimension="timeframe", scope_key=timeframe),
                record=record,
            )
        )

    for regime in _unique_in_order(record.get("regime_refs") or []):
        matrix_rows.append(
            _matrix_row(
                dimension="regime",
                scope_key=regime,
                label=regime,
                inventory_count=1,
                coverage_rows=[],
                record=record,
            )
        )

    for window_ref in _unique_in_order(record.get("window_refs") or []):
        matrix_rows.append(
            _matrix_row(
                dimension="independent_oos_window",
                scope_key=window_ref,
                label=window_ref,
                inventory_count=1,
                coverage_rows=[],
                record=record,
            )
        )

    matrix_rows.sort(key=lambda row: (str(row["dimension"]), str(row["scope_key"])))
    recommendations = _recommendations(matrix_rows)

    dimension_counts = Counter(str(row["dimension"]) for row in matrix_rows)
    supported_hypotheses = sum(int(row["supported_hypothesis_count"]) for row in matrix_rows if row["dimension"] in {"behavior", "preset"})
    rejected_hypotheses = max(1 if record else 0, sum(int(row["rejected_hypothesis_count"]) for row in matrix_rows if row["dimension"] in {"behavior", "preset"}))
    incomplete_hypotheses = sum(int(row["incomplete_hypothesis_count"]) for row in matrix_rows if row["dimension"] in {"behavior", "preset"})
    reproducibility_ready_scope_count = sum(
        1 for row in matrix_rows if row["reproducibility_status"] == "reproducible_authoritative"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "status": "ready",
        "requested_scope": requested,
        "summary": {
            "matrix_row_count": len(matrix_rows),
            "coverage_dimension_counts": dict(sorted(dimension_counts.items())),
            "supported_hypothesis_count": supported_hypotheses,
            "rejected_hypothesis_count": rejected_hypotheses,
            "incomplete_hypothesis_count": incomplete_hypotheses,
            "accepted_lineage_ref_count": len(record.get("accepted_lineage_refs") or []),
            "accepted_oos_ref_count": len(record.get("accepted_oos_refs") or []),
            "independent_window_count": len(record.get("window_refs") or []),
            "regime_count": len(record.get("regime_refs") or []),
            "reproducibility_ready_scope_count": reproducibility_ready_scope_count,
            "breadth_priority_recommendation_count": len(recommendations),
            "operator_summary": (
                "Evidence breadth is mapped as a deterministic read-only coverage matrix across "
                "symbols, baskets, universes, regions, sectors, behaviors, presets, timeframes, "
                "regimes, and independent OOS windows. Correct falsification remains useful maturity evidence."
            ),
        },
        "coverage_matrix": matrix_rows,
        "breadth_priority_recommendations": recommendations,
        "evidence_state": {
            "accepted_lineage_ref_count": len(record.get("accepted_lineage_refs") or []),
            "accepted_oos_ref_count": len(record.get("accepted_oos_refs") or []),
            "rejected_exact_scope_active": bool(record),
            "rejected_hypothesis_id": _text(record.get("hypothesis_id")),
        },
        "authority_flags": {
            "non_authoritative": True,
            "safe_to_execute": False,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "mutates_research_outputs": False,
            "crypto_excluded_without_explicit_authorization": True,
            "profitability_not_used_for_priority": True,
        },
    }
    report["deterministic_hash"] = _digest(
        {
            "schema_version": report["schema_version"],
            "report_kind": report["report_kind"],
            "requested_scope": report["requested_scope"],
            "summary": report["summary"],
            "coverage_matrix": report["coverage_matrix"],
            "breadth_priority_recommendations": report["breadth_priority_recommendations"],
            "evidence_state": report["evidence_state"],
            "authority_flags": report["authority_flags"],
        }
    )
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    recommendations = report.get("breadth_priority_recommendations") if isinstance(report.get("breadth_priority_recommendations"), list) else []
    lines = [
        "# QRE Evidence Breadth Framework",
        "",
        f"- matrix_row_count: {summary.get('matrix_row_count', 0)}",
        f"- supported_hypothesis_count: {summary.get('supported_hypothesis_count', 0)}",
        f"- rejected_hypothesis_count: {summary.get('rejected_hypothesis_count', 0)}",
        f"- incomplete_hypothesis_count: {summary.get('incomplete_hypothesis_count', 0)}",
        f"- accepted_lineage_ref_count: {summary.get('accepted_lineage_ref_count', 0)}",
        f"- accepted_oos_ref_count: {summary.get('accepted_oos_ref_count', 0)}",
        f"- reproducibility_ready_scope_count: {summary.get('reproducibility_ready_scope_count', 0)}",
        "",
        "## Breadth Priorities",
    ]
    if not recommendations:
        lines.append("- none")
    for row in recommendations:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- {row.get('dimension')}::{row.get('scope_key')} score={row.get('priority_score')} "
            f"action={row.get('recommended_next_action')} blockers={','.join(row.get('blocker_reasons', []))}"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    operator_summary = base / OPERATOR_SUMMARY_NAME
    for target in (latest, operator_summary):
        _validate_write_target(target)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    tmp_summary = operator_summary.with_suffix(operator_summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, operator_summary)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": operator_summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_evidence_breadth_framework",
        description="Build a deterministic read-only evidence breadth matrix.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=15)
    args = parser.parse_args(argv)
    report = build_evidence_breadth_framework(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
