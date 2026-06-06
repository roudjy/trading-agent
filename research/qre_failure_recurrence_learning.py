from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import production_discovery_catalog as discovery_catalog
from research import qre_failure_action_from_basket as failure_action
from research import qre_hypothesis_seed_feasibility as hypothesis_feasibility
from research import qre_real_basket_evidence_coverage as evidence_coverage
from research import qre_routing_decision_quality as routing_quality
from research import qre_sampling_decision_quality as sampling_quality


REPORT_KIND: Final[str] = "qre_failure_recurrence_learning"
SOURCE_REPORT_KIND: Final[str] = "qre_source_usefulness_v0"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_failure_recurrence_learning")
SOURCE_OUTPUT_DIR: Final[Path] = Path("logs/qre_source_usefulness_v0")
LATEST_NAME: Final[str] = "latest.json"
_WRITE_PREFIX: Final[str] = "logs/qre_failure_recurrence_learning/"
_SOURCE_WRITE_PREFIX: Final[str] = "logs/qre_source_usefulness_v0/"


def _top_counts(values: Sequence[str], *, limit: int = 5) -> list[dict[str, Any]]:
    counts = Counter(value for value in values if value)
    return [
        {"value": key, "count": counts[key]}
        for key in sorted(counts, key=lambda item: (-counts[item], item))[:limit]
    ]


def _read_only_recommendation(
    *,
    source_blocker_count: int,
    missing_evidence_count: int,
    false_ready_count: int,
    dead_zone_count: int,
) -> str:
    if false_ready_count > 0:
        return "preserve_fail_closed_policy"
    if source_blocker_count > 0:
        return "require_identity_or_source_readiness"
    if dead_zone_count >= 2:
        return "suppress_dead_zone_repeats_until_new_evidence"
    if missing_evidence_count > 0:
        return "collect_more_evidence_before_seed_expansion"
    return "sustain_current_readonly_path"


def _aggregate_dimension(
    rows: Sequence[Mapping[str, Any]],
    *,
    key_name: str,
    label: str,
    extractor: Callable[[Mapping[str, Any]], str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = extractor(row).strip() or "unknown"
        grouped[key].append(row)

    out: list[dict[str, Any]] = []
    for key, members in sorted(grouped.items()):
        dead_zone_count = sum(1 for row in members if bool(row.get("dead_zone")))
        false_ready_count = sum(1 for row in members if bool(row.get("false_ready")))
        source_blocker_count = sum(1 for row in members if bool(row.get("source_blocker")))
        missing_evidence_count = sum(1 for row in members if bool(row.get("missing_evidence")))
        out.append(
            {
                key_name: key,
                "label": label,
                "row_count": len(members),
                "dead_zone_count": dead_zone_count,
                "false_ready_count": false_ready_count,
                "source_blocker_count": source_blocker_count,
                "missing_evidence_count": missing_evidence_count,
                "recommended_actions_top": _top_counts(
                    [str(row.get("recommended_action") or "") for row in members]
                ),
                "read_only_recommendation": _read_only_recommendation(
                    source_blocker_count=source_blocker_count,
                    missing_evidence_count=missing_evidence_count,
                    false_ready_count=false_ready_count,
                    dead_zone_count=dead_zone_count,
                ),
            }
        )
    return out


def build_failure_recurrence_learning(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    coverage_report = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure_report = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    routing_report = routing_quality.build_routing_decision_quality(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling_report = sampling_quality.build_sampling_decision_quality(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    feasibility_report = hypothesis_feasibility.build_hypothesis_seed_feasibility(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    coverage_rows = coverage_report.get("rows")
    if not isinstance(coverage_rows, list):
        coverage_rows = []
    failure_rows = failure_report.get("rows")
    if not isinstance(failure_rows, list):
        failure_rows = []
    routing_rows = routing_report.get("rows")
    if not isinstance(routing_rows, list):
        routing_rows = []
    sampling_rows = sampling_report.get("rows")
    if not isinstance(sampling_rows, list):
        sampling_rows = []
    feasibility_rows = feasibility_report.get("rows")
    if not isinstance(feasibility_rows, list):
        feasibility_rows = []

    failure_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in failure_rows
        if isinstance(row, Mapping)
    }
    routing_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in routing_rows
        if isinstance(row, Mapping)
    }
    sampling_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in sampling_rows
        if isinstance(row, Mapping)
    }
    feasibility_by_hypothesis = {
        str(row.get("hypothesis_id") or ""): row
        for row in feasibility_rows
        if isinstance(row, Mapping)
    }
    asset_catalog = {
        asset.symbol: asset.to_payload() for asset in discovery_catalog.list_assets()
    }

    learning_rows: list[dict[str, Any]] = []
    for row in coverage_rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("candidate_id") or "")
        failure_row = failure_by_subject.get(subject_id, {})
        routing_row = routing_by_subject.get(subject_id, {})
        sampling_row = sampling_by_subject.get(subject_id, {})
        hypothesis_row = feasibility_by_hypothesis.get(str(row.get("hypothesis_id") or ""), {})
        asset_payload = asset_catalog.get(str(row.get("symbol") or ""), {})
        blocker_code = str(failure_row.get("blocker_code") or "")
        recommended_action = str(failure_row.get("recommended_action") or "keep_blocked")
        source_blocker = blocker_code in {
            "source_identity_blocked",
            "source_or_cache_not_ready",
            "source_or_cache_coverage_missing",
        }
        missing_evidence = blocker_code in {
            "source_or_cache_coverage_missing",
            "screening_evidence_missing",
            "oos_evidence_missing",
            "sampling_oos_window_unknown",
            "lineage_missing",
        }
        false_ready = bool(routing_row.get("routing_false_ready")) or bool(
            sampling_row.get("sampling_false_ready")
        )
        dead_zone = (
            recommended_action
            in {
                "collect_more_evidence",
                "expand_basket_coverage",
                "suppress_until_new_evidence",
                "defer_as_duplicate",
            }
            and str(row.get("diagnosis_class") or "") != "diagnosable"
            and not false_ready
        )
        timeframes = row.get("timeframes")
        if not isinstance(timeframes, list) or not timeframes:
            timeframes = ["unknown"]
        learning_rows.append(
            {
                "candidate_id": subject_id,
                "symbol": row.get("symbol"),
                "preset_id": row.get("preset_id"),
                "behavior_family": row.get("behavior_family"),
                "hypothesis_id": row.get("hypothesis_id"),
                "timeframe": str(timeframes[0]),
                "data_source": str(asset_payload.get("data_source") or "unknown"),
                "recommended_action": recommended_action,
                "blocker_code": blocker_code,
                "dead_zone": dead_zone,
                "false_ready": false_ready,
                "source_blocker": source_blocker,
                "missing_evidence": missing_evidence,
                "hypothesis_feasibility_state": hypothesis_row.get("feasibility_state"),
            }
        )

    learning_rows.sort(key=lambda row: (str(row["symbol"]), str(row["preset_id"])))
    asset_rows = _aggregate_dimension(
        learning_rows,
        key_name="symbol",
        label="asset",
        extractor=lambda row: str(row.get("symbol") or ""),
    )
    timeframe_rows = _aggregate_dimension(
        learning_rows,
        key_name="timeframe",
        label="timeframe",
        extractor=lambda row: str(row.get("timeframe") or ""),
    )
    preset_rows = _aggregate_dimension(
        learning_rows,
        key_name="preset_id",
        label="preset",
        extractor=lambda row: str(row.get("preset_id") or ""),
    )
    behavior_rows = _aggregate_dimension(
        learning_rows,
        key_name="behavior_family",
        label="behavior_family",
        extractor=lambda row: str(row.get("behavior_family") or ""),
    )
    source_rows = _aggregate_dimension(
        learning_rows,
        key_name="data_source",
        label="source",
        extractor=lambda row: str(row.get("data_source") or ""),
    )

    false_ready_count = sum(1 for row in learning_rows if bool(row.get("false_ready")))
    source_blocker_recurrence_count = sum(
        1 for row in source_rows if int(row.get("source_blocker_count") or 0) > 0
    )
    missing_evidence_recurrence_count = sum(
        1 for row in preset_rows if int(row.get("missing_evidence_count") or 0) > 0
    )
    repeated_dead_zone_count = sum(
        1 for row in behavior_rows if int(row.get("dead_zone_count") or 0) >= 2
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "max_candidates": max_candidates,
        "summary": {
            "learning_row_count": len(learning_rows),
            "false_ready_count": false_ready_count,
            "source_blocker_recurrence_count": source_blocker_recurrence_count,
            "missing_evidence_recurrence_count": missing_evidence_recurrence_count,
            "repeated_dead_zone_count": repeated_dead_zone_count,
            "read_only_recommendations_top": _top_counts(
                [str(row.get("read_only_recommendation") or "") for row in behavior_rows + source_rows]
            ),
            "final_recommendation": (
                "failure_recurrence_learning_ready"
                if learning_rows
                else "failure_recurrence_learning_missing"
            ),
            "operator_summary": (
                "Failure recurrence learning counts repeated blocked patterns across asset, "
                "timeframe, preset, behavior family, and source without adapting policy."
            ),
        },
        "learning_rows": learning_rows,
        "asset_recurrence_rows": asset_rows,
        "timeframe_recurrence_rows": timeframe_rows,
        "preset_recurrence_rows": preset_rows,
        "behavior_family_recurrence_rows": behavior_rows,
        "source_recurrence_rows": source_rows,
        "safety_invariants": {
            "read_only": True,
            "uses_ml": False,
            "policy_mutation": False,
            "automatic_reroute": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def build_source_usefulness_v0(
    learning_report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    learning_rows = learning_report.get("learning_rows")
    if not isinstance(learning_rows, list):
        learning_rows = []
    asset_catalog = {
        asset.symbol: asset.to_payload() for asset in discovery_catalog.list_assets()
    }

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in learning_rows:
        if not isinstance(row, Mapping):
            continue
        grouped[str(row.get("symbol") or "")].append(row)

    rows: list[dict[str, Any]] = []
    for symbol, members in sorted(grouped.items()):
        asset = asset_catalog.get(symbol, {})
        source_blocker_count = sum(1 for row in members if bool(row.get("source_blocker")))
        false_ready_count = sum(1 for row in members if bool(row.get("false_ready")))
        dead_zone_count = sum(1 for row in members if bool(row.get("dead_zone")))
        ready_path_count = sum(
            1
            for row in members
            if str(row.get("hypothesis_feasibility_state") or "")
            == "feasible_for_readonly_research"
        )
        if ready_path_count > 0:
            usefulness_state = "useful_for_readonly_research"
        elif str(asset.get("source_identity_status") or "") == "candidate_alias_only":
            usefulness_state = "blocked_by_source_identity"
        elif source_blocker_count > 0:
            usefulness_state = "blocked_by_source_or_cache"
        else:
            usefulness_state = "needs_more_evidence"
        rows.append(
            {
                "symbol": symbol,
                "data_source": asset.get("data_source"),
                "provider_symbol_status": asset.get("provider_symbol_status"),
                "source_identity_status": asset.get("source_identity_status"),
                "mapped_basket_count": len(members),
                "source_blocker_count": source_blocker_count,
                "false_ready_count": false_ready_count,
                "dead_zone_count": dead_zone_count,
                "ready_path_count": ready_path_count,
                "usefulness_state": usefulness_state,
                "recommended_action": _read_only_recommendation(
                    source_blocker_count=source_blocker_count,
                    missing_evidence_count=sum(
                        1 for row in members if bool(row.get("missing_evidence"))
                    ),
                    false_ready_count=false_ready_count,
                    dead_zone_count=dead_zone_count,
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": SOURCE_REPORT_KIND,
        "summary": {
            "source_row_count": len(rows),
            "usefulness_state_counts": dict(
                sorted(Counter(str(row["usefulness_state"]) for row in rows).items())
            ),
            "final_recommendation": (
                "source_usefulness_v0_ready" if rows else "source_usefulness_v0_missing"
            ),
            "operator_summary": (
                "Source usefulness v0 summarizes which mapped symbols currently help "
                "read-only research versus staying blocked by identity, cache, or thin evidence."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "policy_mutation": False,
            "source_lifecycle_automation": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path, prefix: str, *, label: str) -> None:
    if prefix not in path.as_posix():
        raise ValueError(f"{label}: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    source_report = build_source_usefulness_v0(report, repo_root=repo_root)
    main_dir = repo_root / DEFAULT_OUTPUT_DIR
    source_dir = repo_root / SOURCE_OUTPUT_DIR
    main_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    latest = main_dir / LATEST_NAME
    source_latest = source_dir / LATEST_NAME
    _validate_write_target(latest, _WRITE_PREFIX, label="qre_failure_recurrence_learning")
    _validate_write_target(
        source_latest,
        _SOURCE_WRITE_PREFIX,
        label="qre_source_usefulness_v0",
    )
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)
    tmp_source = source_latest.with_suffix(source_latest.suffix + ".tmp")
    tmp_source.write_text(
        json.dumps(source_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_source, source_latest)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "source_usefulness_v0": source_latest.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_failure_recurrence_learning",
        description="Build read-only QRE failure recurrence learning metrics.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_failure_recurrence_learning(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
