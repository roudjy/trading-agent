from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal

from research.candidate_returns_feed import CandidateReturnsRecord
from research.portfolio_diagnostics import compute_diagnostics
from research.qre_candidate_quality_framework import build_candidate_quality_framework
from research.qre_evidence_breadth_framework import build_evidence_breadth_framework
from research.sleeve_registry import assign_sleeves
from research import production_discovery_catalog as discovery_catalog


PortfolioStatus = Literal[
    "blocked_no_candidates",
    "blocked_no_accepted_oos",
    "blocked_insufficient_comparable_history",
    "blocked_scope_mismatch",
    "blocked_missing_correlation_evidence",
    "blocked_missing_liquidity_evidence",
    "portfolio_research_context_ready",
]

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_multibasket_portfolio_intelligence"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_multibasket_portfolio_intelligence")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_multibasket_portfolio_intelligence/"
DEFAULT_QUALITY_PATH: Final[Path] = Path("logs/qre_candidate_quality_framework/latest.json")
DEFAULT_BREADTH_PATH: Final[Path] = Path("logs/qre_evidence_breadth_framework/latest.json")
MIN_COMPARABLE_CANDIDATES: Final[int] = 2
MIN_COMPARABLE_OBSERVATIONS: Final[int] = 5


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _breadth_index(breadth_report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = breadth_report.get("coverage_matrix") if isinstance(breadth_report.get("coverage_matrix"), list) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if _text(row.get("dimension")) != "basket":
            continue
        out[_text(row.get("scope_key"))] = dict(row)
    return out


def _asset_lookup() -> dict[str, dict[str, Any]]:
    return {
        _text(payload.get("symbol")): payload
        for payload in (asset.to_payload() for asset in discovery_catalog.list_assets())
        if _text(payload.get("symbol"))
    }


def _scope_components(scope_key: str) -> dict[str, str]:
    parts = [part for part in scope_key.split("::") if part]
    preset_id = parts[1] if len(parts) >= 2 else ""
    symbol = parts[2] if len(parts) >= 3 else ""
    timeframe = "unknown_timeframe"
    for candidate in ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "daily", "weekly"):
        needle = f"_{candidate}_"
        if needle in f"_{preset_id}_":
            timeframe = "1d" if candidate == "daily" else candidate
            break
    behavior_id = preset_id
    for suffix in ("_daily_v1", "_4h_v1", "_1d_v1", "_weekly_v1", "_v1"):
        if behavior_id.endswith(suffix):
            behavior_id = behavior_id[: -len(suffix)]
            break
    return {
        "preset_id": preset_id or "unknown_preset",
        "symbol": symbol or "unknown_symbol",
        "timeframe": timeframe,
        "behavior_id": behavior_id or "unknown_behavior",
    }


def _scope_key(quality_row: Mapping[str, Any]) -> str:
    return _text(quality_row.get("scope_key")) or _text(quality_row.get("source_scope_ref")).removeprefix("coverage_matrix::")


def _context_row(
    quality_row: Mapping[str, Any],
    breadth_row: Mapping[str, Any] | None,
    *,
    asset_lookup: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    width = breadth_row or {}
    scope_components = _scope_components(_scope_key(quality_row))
    symbol = _text(width.get("symbol")) or scope_components["symbol"]
    asset = asset_lookup.get(symbol, {})
    return {
        "candidate_id": _text(quality_row.get("candidate_id")),
        "quality_status": _text(quality_row.get("quality_status")),
        "lifecycle_status": _text(quality_row.get("lifecycle_status")),
        "scope_key": _scope_key(quality_row),
        "hypothesis_id": _text(width.get("hypothesis_id")) or scope_components["preset_id"],
        "behavior_id": _text(width.get("behavior_id")) or scope_components["behavior_id"],
        "region": _text(width.get("region")) or _text(asset.get("region")) or "unknown_region",
        "sector": _text(width.get("sector")) or _text(asset.get("sector")) or "unknown_sector",
        "symbol": symbol,
        "timeframe": _text(width.get("timeframe")) or scope_components["timeframe"],
        "scope_label": _text(width.get("scope_label")) or _scope_key(quality_row),
        "universe_scope": _text(width.get("scope_label")) or _scope_key(quality_row),
        "accepted_oos_count": int(quality_row.get("accepted_oos_count") or 0),
        "accepted_lineage_count": int(quality_row.get("accepted_lineage_count") or 0),
        "blocker_codes": list(quality_row.get("blocker_codes") or []),
        "source_quality_passed": bool(
            (((quality_row.get("quality_dimensions") or {}).get("source_quality")) or {}).get("passed")
        ),
        "regime_overlap_refs": list(width.get("regime_refs") or []),
        "liquidity_source_refs": list(width.get("source_refs") or []),
        "capacity_proxy": width.get("capacity_proxy"),
    }


def _build_context_rows(
    quality_report: Mapping[str, Any],
    breadth_report: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    quality_rows = quality_report.get("rows") if isinstance(quality_report.get("rows"), list) else []
    breadth_by_scope = _breadth_index(breadth_report)
    asset_lookup = _asset_lookup()
    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for row in quality_rows:
        if not isinstance(row, Mapping):
            continue
        scope_key = _scope_key(row)
        breadth_row = breadth_by_scope.get(scope_key)
        if breadth_row is None:
            mismatches.append(scope_key)
        rows.append(_context_row(row, breadth_row, asset_lookup=asset_lookup))
    rows.sort(key=lambda row: row["candidate_id"])
    return rows, mismatches


def _pair_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    comparisons = {
        "behavior_overlap": _text(left.get("behavior_id")) == _text(right.get("behavior_id")),
        "hypothesis_overlap": _text(left.get("hypothesis_id")) == _text(right.get("hypothesis_id")),
        "region_overlap": _text(left.get("region")) == _text(right.get("region")),
        "sector_overlap": _text(left.get("sector")) == _text(right.get("sector")),
        "timeframe_overlap": _text(left.get("timeframe")) == _text(right.get("timeframe")),
        "scope_overlap": _text(left.get("scope_key")) == _text(right.get("scope_key")),
        "signal_overlap": (
            _text(left.get("behavior_id")) == _text(right.get("behavior_id"))
            and _text(left.get("timeframe")) == _text(right.get("timeframe"))
        ),
    }
    overlap_score = round(
        sum(1 for value in comparisons.values() if value) / len(comparisons),
        6,
    )
    return {
        "left_candidate_id": left["candidate_id"],
        "right_candidate_id": right["candidate_id"],
        **comparisons,
        "overlap_score": overlap_score,
    }


def _pairwise_overlap(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, left in enumerate(rows):
        for right in rows[idx + 1 :]:
            out.append(_pair_overlap(left, right))
    out.sort(key=lambda row: (row["left_candidate_id"], row["right_candidate_id"]))
    return out


def _count_dimension(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counter = Counter(_text(row.get(field)) or f"unknown_{field}" for row in rows)
    return dict(sorted(counter.items()))


def _contradictions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(_text(row.get("behavior_id")), _text(row.get("timeframe")))].append(row)
    out: list[dict[str, Any]] = []
    for (behavior_id, timeframe), members in sorted(grouped.items()):
        statuses = sorted({_text(member.get("quality_status")) for member in members})
        if len(statuses) <= 1:
            continue
        out.append(
            {
                "behavior_id": behavior_id,
                "timeframe": timeframe,
                "quality_statuses": statuses,
                "candidate_ids": sorted(_text(member.get("candidate_id")) for member in members),
            }
        )
    return out


def _returns_record(candidate_id: str, values: Sequence[float]) -> CandidateReturnsRecord:
    data = tuple(float(value) for value in values)
    return CandidateReturnsRecord(
        candidate_id=candidate_id,
        daily_returns=data,
        n_obs=len(data),
        start_date=None,
        end_date=None,
        insufficient_returns=len(data) == 0,
    )


def _registry_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    region = _text(row.get("region")) or "unknown_region"
    return {
        "candidate_id": _text(row.get("candidate_id")),
        "asset": region,
        "experiment_family": f"{_text(row.get('behavior_id'))}|equities",
        "interval": _text(row.get("timeframe")) or "unknown_timeframe",
        "lifecycle_status": "candidate",
    }


def _correlation_block(
    candidates: Sequence[Mapping[str, Any]],
    *,
    candidate_returns: Mapping[str, Sequence[float]] | None,
) -> dict[str, Any]:
    if len(candidates) < MIN_COMPARABLE_CANDIDATES:
        return {
            "status": "blocked_no_candidates",
            "missing_evidence": ["fewer_than_two_candidates"],
            "diagnostics": {},
        }
    if not isinstance(candidate_returns, Mapping):
        return {
            "status": "blocked_missing_correlation_evidence",
            "missing_evidence": ["candidate_returns_missing"],
            "diagnostics": {},
        }
    records: list[CandidateReturnsRecord] = []
    included_rows: list[Mapping[str, Any]] = []
    for row in candidates:
        candidate_id = _text(row.get("candidate_id"))
        values = candidate_returns.get(candidate_id)
        if not isinstance(values, Sequence):
            continue
        values = [float(value) for value in values]
        if len(values) < MIN_COMPARABLE_OBSERVATIONS:
            continue
        records.append(_returns_record(candidate_id, values))
        included_rows.append(row)
    if len(records) < MIN_COMPARABLE_CANDIDATES:
        return {
            "status": "blocked_insufficient_comparable_history",
            "missing_evidence": ["comparable_return_history_below_minimum"],
            "diagnostics": {},
        }
    registry_v2 = {"entries": [_registry_entry(row) for row in included_rows]}
    sleeves = assign_sleeves(registry_v2=registry_v2)
    diagnostics = compute_diagnostics(
        registry_v2=registry_v2,
        sleeve_registry=sleeves,
        candidate_returns=records,
    )
    return {
        "status": "portfolio_research_context_ready",
        "missing_evidence": [],
        "diagnostics": diagnostics,
    }


def build_multibasket_portfolio_intelligence(
    *,
    quality_report: Mapping[str, Any],
    breadth_report: Mapping[str, Any],
    candidate_returns: Mapping[str, Sequence[float]] | None = None,
) -> dict[str, Any]:
    context_rows, scope_mismatches = _build_context_rows(quality_report, breadth_report)
    if not context_rows:
        report = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "summary": {
                "status": "blocked_no_candidates",
                "context_status": "blocked_no_candidates",
                "candidate_count": 0,
                "production_candidate_count": 0,
                "final_recommendation": "portfolio_research_fail_closed",
                "operator_summary": (
                    "No candidate-quality rows are available, so multi-basket portfolio intelligence "
                    "remains blocked."
                ),
            },
            "context_rows": [],
            "pairwise_overlap": [],
            "concentration": {},
            "contradictions": [],
            "missing_evidence": ["candidate_quality_rows_missing"],
            "authority": {
                "non_authoritative": True,
                "capital_allocation_forbidden": True,
                "order_generation_forbidden": True,
                "promotion_forbidden": True,
            },
            "safety_invariants": {
                "read_only": True,
                "portfolio_weights_forbidden": True,
                "capital_allocation_forbidden": True,
                "risk_runtime_forbidden": True,
                "promotion_forbidden": True,
            },
        }
        report["deterministic_hash"] = _digest(report)
        return report

    production_candidates = [
        row
        for row in context_rows
        if row["quality_status"] == "eligible_for_operator_quality_review" and int(row["accepted_oos_count"]) > 0
    ]
    max_accepted_oos = max(int(row["accepted_oos_count"]) for row in context_rows)
    overall_status: PortfolioStatus = (
        "blocked_no_accepted_oos" if max_accepted_oos == 0 else "blocked_no_candidates"
    )
    missing_evidence = ["accepted_oos_candidates_missing"] if max_accepted_oos == 0 else ["eligible_candidates_missing"]
    if scope_mismatches:
        overall_status = "blocked_scope_mismatch"
        missing_evidence = [f"scope_missing_from_breadth:{scope}" for scope in sorted(scope_mismatches)]

    correlation = _correlation_block(production_candidates, candidate_returns=candidate_returns)
    liquidity_status: PortfolioStatus = (
        "portfolio_research_context_ready"
        if all(row["liquidity_source_refs"] for row in production_candidates)
        else "blocked_missing_liquidity_evidence"
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "status": overall_status,
            "context_status": "portfolio_research_context_ready",
            "candidate_count": len(context_rows),
            "production_candidate_count": len(production_candidates),
            "eligible_candidate_count": sum(
                1 for row in context_rows if row["quality_status"] == "eligible_for_operator_quality_review"
            ),
            "final_recommendation": "portfolio_research_fail_closed",
            "operator_summary": (
                "Portfolio intelligence is read-only context. Without accepted OOS quality candidates, "
                "production portfolio research remains blocked while overlap and concentration context stays visible."
            ),
        },
        "context_rows": context_rows,
        "pairwise_overlap": _pairwise_overlap(context_rows),
        "concentration": {
            "behavior": _count_dimension(context_rows, "behavior_id"),
            "region": _count_dimension(context_rows, "region"),
            "sector": _count_dimension(context_rows, "sector"),
            "symbol": _count_dimension(context_rows, "symbol"),
            "timeframe": _count_dimension(context_rows, "timeframe"),
            "universe_scope": _count_dimension(context_rows, "universe_scope"),
        },
        "correlation": correlation,
        "liquidity_overlap": {
            "status": liquidity_status,
            "ready_candidate_count": sum(1 for row in production_candidates if row["liquidity_source_refs"]),
        },
        "capacity_proxies": {
            "status": (
                "portfolio_research_context_ready"
                if all(row["capacity_proxy"] is not None for row in production_candidates) and production_candidates
                else "blocked_missing_liquidity_evidence"
            ),
            "present_candidate_count": sum(1 for row in production_candidates if row["capacity_proxy"] is not None),
        },
        "diversification": (
            ((correlation.get("diagnostics") or {}).get("equal_weight_portfolio") or {})
            if correlation["status"] == "portfolio_research_context_ready"
            else {
                "status": "blocked_missing_correlation_evidence",
                "candidate_count": len(production_candidates),
            }
        ),
        "contradictions": _contradictions(context_rows),
        "missing_evidence": sorted(set(missing_evidence + list(correlation["missing_evidence"]))),
        "authority": {
            "non_authoritative": True,
            "capital_allocation_forbidden": True,
            "order_generation_forbidden": True,
            "promotion_forbidden": True,
            "risk_budget_forbidden": True,
        },
        "safety_invariants": {
            "read_only": True,
            "portfolio_weights_forbidden": True,
            "capital_allocation_forbidden": True,
            "risk_runtime_forbidden": True,
            "promotion_forbidden": True,
            "fixture_evidence_not_authoritative": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def build_portfolio_intelligence_report(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    quality_report = _read_json(repo_root / DEFAULT_QUALITY_PATH) or build_candidate_quality_framework(
        repo_root=repo_root
    )
    breadth_report = _read_json(repo_root / DEFAULT_BREADTH_PATH) or build_evidence_breadth_framework(
        repo_root=repo_root
    )
    return build_multibasket_portfolio_intelligence(
        quality_report=quality_report,
        breadth_report=breadth_report,
        candidate_returns=None,
    )


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Multi-Basket Portfolio Intelligence",
            "",
            f"- status: {summary.get('status') or 'unknown'}",
            f"- context_status: {summary.get('context_status') or 'unknown'}",
            f"- candidate_count: {summary.get('candidate_count') or 0}",
            f"- production_candidate_count: {summary.get('production_candidate_count') or 0}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": _rel(latest, root=repo_root),
        "operator_summary": _rel(summary_path, root=repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_multibasket_portfolio_intelligence",
        description="Build read-only QRE multi-basket portfolio intelligence.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_portfolio_intelligence_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
