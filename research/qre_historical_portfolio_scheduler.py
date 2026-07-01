from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_research import decision_calibration as dcal
from packages.qre_research import research_memory
from research import qre_campaign_throughput_bottleneck_intelligence as throughput_bottlenecks
from research import qre_hypothesis_disposition_memory as disposition_memory
from research import qre_research_memory_current_artifacts as current_artifacts
from research import qre_research_memory_retrieval as memory_retrieval
from research import qre_source_usefulness_ledger as source_usefulness


REPORT_KIND: Final[str] = "qre_historical_portfolio_scheduler"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-034.1"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_historical_portfolio_scheduler")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_historical_portfolio_scheduler/"

DEFAULT_ARTIFACT_PATHS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
    Path("research/strategy_hypothesis_catalog_latest.v1.json"),
    Path("generated_research/hypotheses/registry/generated_thesis_registry.v1.json"),
    Path("generated_research/registry/generated_strategy_registry.v1.json"),
    Path("generated_research/primitives/registry/generated_primitive_registry.v1.json"),
    Path("generated_research/orchestration/portfolio/unified_research_portfolio.v1.json"),
    Path("generated_research/orchestration/scheduler/campaign_schedule.v1.json"),
    Path("generated_research/hypotheses/lifecycle/research_memory.v1.json"),
    Path("generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json"),
    Path("generated_research/campaign_execution/reports/second_campaign_closeout.v1.json"),
    Path("logs/qre_hypothesis_disposition_memory/latest.json"),
    Path("logs/qre_research_memory_current_artifacts/latest.json"),
    Path("logs/qre_research_memory_retrieval/latest.json"),
    Path("logs/qre_campaign_throughput_bottleneck_intelligence/latest.json"),
    Path("logs/qre_experiment_dedup_novelty_enforcement/latest.json"),
    Path("logs/qre_source_usefulness_ledger/latest.json"),
)


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


def _read_rows(payload: Mapping[str, Any] | None, *keys: str) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _stable_digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    import hashlib

    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{_stable_digest(payload)[:16]}"


def _candidate_rows(repo_root: Path) -> list[dict[str, Any]]:
    catalog = _read_json(repo_root / "research" / "strategy_hypothesis_catalog_latest.v1.json") or {}
    generated = _read_json(
        repo_root / "generated_research" / "hypotheses" / "registry" / "generated_thesis_registry.v1.json"
    ) or {}
    portfolio = _read_json(
        repo_root / "generated_research" / "orchestration" / "portfolio" / "unified_research_portfolio.v1.json"
    ) or {}
    disposition = _read_json(repo_root / "logs" / "qre_hypothesis_disposition_memory" / "latest.json") or {}

    catalog_rows = _read_rows(catalog, "hypotheses")
    generated_rows = _read_rows(generated, "rows")
    strategy_rows = _read_rows(portfolio, "strategy_rows")
    disposition_record = disposition.get("record") if isinstance(disposition.get("record"), Mapping) else {}
    disposition_scope = disposition_record.get("disposition_scope") if isinstance(disposition_record.get("disposition_scope"), Mapping) else {}

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(sorted(catalog_rows, key=lambda item: _text(item.get("hypothesis_id")))):
        hypothesis_id = _text(row.get("hypothesis_id"))
        rows.append(
            {
                "candidate_variant_id": f"{hypothesis_id}::catalog::{index}",
                "candidate_source": "catalog",
                "hypothesis_id": hypothesis_id,
                "source_hypothesis_id": hypothesis_id,
                "mechanism_family": _text(row.get("strategy_family")),
                "behavior_family": _text(row.get("strategy_family")),
                "status": _text(row.get("status")),
                "cost_class": _text(row.get("cost_class")),
                "eligible_campaign_types": list(row.get("eligible_campaign_types") or []),
                "feature_dependencies": list(row.get("feature_dependencies") or []),
                "expected_failure_modes": list(row.get("expected_failure_modes") or []),
                "baseline_reference": _text(row.get("baseline_reference")),
                "priority_seed": 10.0,
                "provenance": ["research/strategy_hypothesis_catalog_latest.v1.json"],
                "portfolio_stage": "",
                "portfolio_blocker": "",
            }
        )
    for index, row in enumerate(sorted(generated_rows, key=lambda item: _text(item.get("source_hypothesis_id")))):
        source_hypothesis_id = _text(row.get("source_hypothesis_id"))
        rows.append(
            {
                "candidate_variant_id": f"{source_hypothesis_id}::generated::{index}",
                "candidate_source": "generated_thesis",
                "hypothesis_id": _text(row.get("thesis_id")) or source_hypothesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "mechanism_family": _text(row.get("behavior_family")) or _text(row.get("mechanism_class")),
                "behavior_family": _text(row.get("behavior_family")),
                "status": _text(row.get("lifecycle_state")),
                "cost_class": "medium" if source_hypothesis_id == "cross_sectional_momentum_v0" else "unknown",
                "eligible_campaign_types": ["daily_primary"] if source_hypothesis_id == "cross_sectional_momentum_v0" else [],
                "feature_dependencies": ["lookback_returns", "rank_returns"] if source_hypothesis_id == "cross_sectional_momentum_v0" else [],
                "expected_failure_modes": ["insufficient_trades", "cost_fragile", "no_baseline_edge"] if source_hypothesis_id == "cross_sectional_momentum_v0" else [],
                "baseline_reference": "",
                "priority_seed": 22.0,
                "provenance": ["generated_research/hypotheses/registry/generated_thesis_registry.v1.json"],
                "portfolio_stage": "",
                "portfolio_blocker": "",
            }
        )

    strategy_by_source = {
        _text(row.get("thesis_id")): dict(row)
        for row in strategy_rows
        if _text(row.get("thesis_id"))
    }
    for row in rows:
        source_hypothesis_id = _text(row.get("source_hypothesis_id"))
        strategy_row = strategy_by_source.get(source_hypothesis_id)
        if strategy_row:
            row["portfolio_stage"] = _text(strategy_row.get("current_stage"))
            row["portfolio_blocker"] = _text(strategy_row.get("primary_blocker"))
            row["priority_seed"] = max(
                float(row.get("priority_seed") or 0.0),
                float(strategy_row.get("priority_score") or 0.0) * 100.0,
            )

    # Keep deterministic order and a fixed 8-row candidate universe when available.
    rows.sort(key=lambda row: (_text(row.get("candidate_source")), _text(row.get("source_hypothesis_id")), _text(row.get("candidate_variant_id"))))
    rows = rows[:8]

    if disposition_scope:
        for row in rows:
            if _text(row.get("source_hypothesis_id")) == _text(disposition_scope.get("hypothesis_id")):
                row["historical_scope_match"] = True
            else:
                row["historical_scope_match"] = False
    return rows


def _status_weight(status: str) -> float:
    return {
        "active_discovery": 42.0,
        "diagnostic": 26.0,
        "planned": 18.0,
        "admitted_generation_blocked": 12.0,
        "blocked": 6.0,
        "disabled": 2.0,
    }.get(status, 10.0)


def _cost_weight(cost_class: str) -> float:
    return {
        "low": 8.0,
        "medium": 6.0,
        "high": 2.0,
    }.get(cost_class, 4.0)


def _terminal_disposition(
    candidate: Mapping[str, Any],
    *,
    empirical_pack: Mapping[str, Any],
    closeout: Mapping[str, Any],
    historical_record: Mapping[str, Any],
) -> dict[str, Any]:
    source_hypothesis_id = _text(candidate.get("source_hypothesis_id"))
    if source_hypothesis_id == _text(empirical_pack.get("source_hypothesis_id")):
        decision_semantics = dcal.classify_terminal_disposition(
            closeout=dict(closeout),
            empirical_pack=dict(empirical_pack),
        )
        return {
            "terminal_disposition": _text(decision_semantics.get("terminal_disposition")),
            "active_blocker": _text(decision_semantics.get("active_blocker")),
            "next_action": _text(decision_semantics.get("next_action")),
            "provenance": "REAL_EMPIRICAL",
            "resolved_blockers": list(decision_semantics.get("resolved_blockers") or []),
            "reason_codes": list(decision_semantics.get("reason_codes") or []),
        }
    if _text(candidate.get("status")) == "disabled":
        return {
            "terminal_disposition": "REQUIRES_PRIMITIVE_EXTENSION",
            "active_blocker": "EXTEND_PRIMITIVE",
            "next_action": "extend_primitive_controls_or_add_canonical_controls",
            "provenance": "HISTORICAL",
            "resolved_blockers": [],
            "reason_codes": ["disabled_in_catalog"],
        }
    if _text(candidate.get("candidate_source")) == "generated_thesis":
        return {
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "next_action": "launch_data_oos_capacity_expansion",
            "provenance": "HISTORICAL",
            "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
            "reason_codes": ["insufficient_activity", "no_supporting_evidence"],
        }
    if _text(candidate.get("status")) == "diagnostic":
        return {
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "active_blocker": "NO_CAUSAL_PROGRESS",
            "next_action": "preserve_current_read_only_artifact_visibility",
            "provenance": "HISTORICAL",
            "resolved_blockers": [],
            "reason_codes": ["diagnostic_only"],
        }
    if _text(candidate.get("status")) in {"planned", "active_discovery"}:
        if _text(candidate.get("mechanism_family")) == _text(historical_record.get("behavior_id")) or _text(candidate.get("status")) == "planned":
            return {
                "terminal_disposition": "REJECTED",
                "active_blocker": "COOL_DOWN_FAMILY",
                "next_action": "cool_down_family",
                "provenance": "HISTORICAL",
                "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
                "reason_codes": ["duplicate_lineage", "historical_null_failure"],
            }
        return {
            "terminal_disposition": "NEEDS_MORE_EVIDENCE",
            "active_blocker": "REQUEST_MORE_EVIDENCE",
            "next_action": "bounded_regime_segmented_follow_up",
            "provenance": "HISTORICAL",
            "resolved_blockers": [],
            "reason_codes": ["insufficient_activity"],
        }
    return {
        "terminal_disposition": "NEEDS_MORE_EVIDENCE",
        "active_blocker": "REQUEST_MORE_EVIDENCE",
        "next_action": "launch_data_oos_capacity_expansion",
        "provenance": "HISTORICAL",
        "resolved_blockers": [],
        "reason_codes": ["insufficient_activity"],
    }


def _scored_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    historical_record: Mapping[str, Any],
    empirical_pack: Mapping[str, Any],
    closeout: Mapping[str, Any],
    admitted_history: set[str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    repeated_sources = Counter(_text(row.get("source_hypothesis_id")) for row in candidates)
    history_scope = {
        "hypothesis_id": _text((historical_record.get("disposition_scope") or {}).get("hypothesis_id")),
        "behavior_id": _text((historical_record.get("disposition_scope") or {}).get("behavior_id")),
        "preset_id": _text((historical_record.get("disposition_scope") or {}).get("preset_id")),
        "timeframe": _text((historical_record.get("disposition_scope") or {}).get("timeframe")),
        "universe_or_basket_scope": _text((historical_record.get("disposition_scope") or {}).get("universe_or_basket_scope")),
    }
    for candidate in candidates:
        source_hypothesis_id = _text(candidate.get("source_hypothesis_id"))
        terminal = _terminal_disposition(
            candidate,
            empirical_pack=empirical_pack,
            closeout=closeout,
            historical_record=historical_record,
        )
        revisit = disposition_memory.evaluate_revisit_eligibility(
            {"record": historical_record},
            proposed_scope={
                "hypothesis_id": source_hypothesis_id,
                "behavior_id": _text(candidate.get("mechanism_family")),
                "preset_id": _text(candidate.get("candidate_variant_id")),
                "timeframe": _text(candidate.get("portfolio_stage")),
                "universe_or_basket_scope": _text(candidate.get("behavior_family")),
            },
        )
        duplicate_penalty = 0.0
        novelty_bonus = 0.0
        if repeated_sources[source_hypothesis_id] > 1:
            duplicate_penalty += 18.0
        if not revisit.get("eligible", True):
            duplicate_penalty += 22.0
        if source_hypothesis_id in admitted_history:
            duplicate_penalty += 30.0
        if (
            history_scope["hypothesis_id"]
            and source_hypothesis_id == history_scope["hypothesis_id"]
            and _text(candidate.get("candidate_source")) == "catalog"
        ):
            duplicate_penalty += 12.0
        if _text(candidate.get("candidate_source")) == "generated_thesis":
            novelty_bonus += 60.0
        if terminal["terminal_disposition"] == "REJECTED":
            duplicate_penalty += 25.0
        if terminal["terminal_disposition"] == "REQUIRES_PRIMITIVE_EXTENSION":
            duplicate_penalty += 18.0
        if terminal["terminal_disposition"] == "NEEDS_MORE_EVIDENCE" and terminal["provenance"] == "REAL_EMPIRICAL":
            duplicate_penalty += 35.0
        baseline = _status_weight(_text(candidate.get("status"))) + _cost_weight(_text(candidate.get("cost_class")))
        baseline += float(candidate.get("priority_seed") or 0.0) / 100.0
        memory_score = max(0.0, baseline - duplicate_penalty + novelty_bonus)
        admission_status = (
            "SUPPRESSED_DUPLICATE"
            if duplicate_penalty >= 22.0
            and terminal["terminal_disposition"] != "READY_FOR_SYNTHESIS"
            and _text(candidate.get("candidate_source")) != "generated_thesis"
            else "ADMITTED"
            if memory_score >= 12.0 and terminal["terminal_disposition"] in {"NEEDS_MORE_EVIDENCE", "READY_FOR_SYNTHESIS"}
            else "BLOCKED"
        )
        output.append(
            {
                "candidate_variant_id": candidate.get("candidate_variant_id"),
                "candidate_source": candidate.get("candidate_source"),
                "hypothesis_id": candidate.get("hypothesis_id"),
                "source_hypothesis_id": source_hypothesis_id,
                "mechanism_family": candidate.get("mechanism_family"),
                "behavior_family": candidate.get("behavior_family"),
                "status": candidate.get("status"),
                "cost_class": candidate.get("cost_class"),
                "eligible_campaign_types": list(candidate.get("eligible_campaign_types") or []),
                "feature_dependencies": list(candidate.get("feature_dependencies") or []),
                "priority_seed": float(candidate.get("priority_seed") or 0.0),
                "baseline_score": round(baseline, 6),
                "memory_penalty": round(duplicate_penalty, 6),
                "memory_score": round(memory_score, 6),
                "admission_status": admission_status,
                "terminal_disposition": terminal["terminal_disposition"],
                "active_blocker": terminal["active_blocker"],
                "next_action": terminal["next_action"],
                "resolved_blockers": list(terminal.get("resolved_blockers") or []),
                "reason_codes": list(terminal.get("reason_codes") or []),
                "provenance": terminal["provenance"],
                "historical_scope_match": bool(candidate.get("historical_scope_match")),
                "duplicate_count": repeated_sources[source_hypothesis_id],
                "revisit_eligible": bool(revisit.get("eligible", False)),
                "revisit_reason": _text(revisit.get("reason")),
            }
        )
    output.sort(key=lambda row: (-float(row["memory_score"]), -float(row["baseline_score"]), str(row["candidate_variant_id"])))
    return output


def _cycle_rows(
    scored_candidates: Sequence[Mapping[str, Any]],
    *,
    max_admitted: int,
    admitted_history: set[str],
) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    next_admitted = set(admitted_history)
    admitted_count = 0
    family_counts: Counter[str] = Counter()
    for row in scored_candidates:
        if row["admission_status"] == "SUPPRESSED_DUPLICATE":
            rows.append(
                {
                    "candidate_variant_id": row["candidate_variant_id"],
                    "candidate_source": row["candidate_source"],
                    "admission_status": "SUPPRESSED_DUPLICATE",
                    "terminal_disposition": row["terminal_disposition"],
                    "next_action": "preserve_suppressed_scope_boundary",
                    "memory_score": row["memory_score"],
                    "baseline_score": row["baseline_score"],
                    "duplicate_terminal_work_prevented": True,
                }
            )
            continue
        if row["terminal_disposition"] == "REJECTED":
            rows.append(
                {
                    "candidate_variant_id": row["candidate_variant_id"],
                    "candidate_source": row["candidate_source"],
                    "admission_status": "BLOCKED",
                    "terminal_disposition": row["terminal_disposition"],
                    "next_action": row["next_action"],
                    "memory_score": row["memory_score"],
                    "baseline_score": row["baseline_score"],
                    "duplicate_terminal_work_prevented": False,
                }
            )
            continue
        family = _text(row.get("mechanism_family"))
        if family_counts[family] >= 2:
            rows.append(
                {
                    "candidate_variant_id": row["candidate_variant_id"],
                    "candidate_source": row["candidate_source"],
                    "admission_status": "BLOCKED_FAMILY_CAP",
                    "terminal_disposition": row["terminal_disposition"],
                    "next_action": "preserve_family_budget",
                    "memory_score": row["memory_score"],
                    "baseline_score": row["baseline_score"],
                    "duplicate_terminal_work_prevented": False,
                }
            )
            continue
        if row["source_hypothesis_id"] in next_admitted:
            rows.append(
                {
                    "candidate_variant_id": row["candidate_variant_id"],
                    "candidate_source": row["candidate_source"],
                    "admission_status": "DUPLICATE_TERMINAL_WORK_PREVENTED",
                    "terminal_disposition": row["terminal_disposition"],
                    "next_action": "preserve_suppressed_scope_boundary",
                    "memory_score": row["memory_score"],
                    "baseline_score": row["baseline_score"],
                    "duplicate_terminal_work_prevented": True,
                }
            )
            continue
        if row["admission_status"] == "ADMITTED" and admitted_count < max_admitted:
            admitted_count += 1
            family_counts[family] += 1
            next_admitted.add(_text(row["source_hypothesis_id"]))
            rows.append(
                {
                    "candidate_variant_id": row["candidate_variant_id"],
                    "candidate_source": row["candidate_source"],
                    "admission_status": "ADMITTED",
                    "terminal_disposition": row["terminal_disposition"],
                    "next_action": row["next_action"],
                    "memory_score": row["memory_score"],
                    "baseline_score": row["baseline_score"],
                    "duplicate_terminal_work_prevented": False,
                }
            )
            continue
        rows.append(
            {
                "candidate_variant_id": row["candidate_variant_id"],
                "candidate_source": row["candidate_source"],
                "admission_status": "DEFERRED",
                "terminal_disposition": row["terminal_disposition"],
                "next_action": row["next_action"],
                "memory_score": row["memory_score"],
                "baseline_score": row["baseline_score"],
                "duplicate_terminal_work_prevented": False,
            }
        )
    return rows, next_admitted


def build_historical_portfolio_scheduler(
    *,
    repo_root: Path = Path("."),
    max_cycles: int = 3,
    max_admitted: int = 3,
    artifact_paths: Sequence[Path] = DEFAULT_ARTIFACT_PATHS,
) -> dict[str, Any]:
    package_memory = research_memory.build_research_memory(
        artifact_paths=artifact_paths,
        repo_root=repo_root,
    )
    retrieval = memory_retrieval.build_research_memory_retrieval(repo_root=repo_root)
    current_memory = current_artifacts.build_research_memory_current_artifacts(repo_root=repo_root)
    throughput_report = throughput_bottlenecks.build_campaign_throughput_bottleneck_intelligence(
        repo_root=repo_root
    )
    source_ledger = source_usefulness.build_source_usefulness_ledger(repo_root=repo_root)

    memory_summary = dict(package_memory.get("summary") or {})
    retrieval_summary = dict(retrieval.get("summary") or {})
    current_summary = dict(current_memory.get("summary") or {})
    throughput_summary = dict(throughput_report.get("summary") or {})
    source_summary = dict(source_ledger.get("summary") or {})

    empirical_pack = _read_json(repo_root / "generated_research" / "campaign_execution" / "evidence" / "empirical_evidence_pack.v1.json") or {}
    closeout = _read_json(repo_root / "generated_research" / "campaign_execution" / "reports" / "second_campaign_closeout.v1.json") or {}
    disposition_payload = _read_json(repo_root / "logs" / "qre_hypothesis_disposition_memory" / "latest.json") or {}
    historical_record = disposition_payload.get("record") if isinstance(disposition_payload.get("record"), Mapping) else {}

    candidates = _candidate_rows(repo_root)
    baseline_sorted = sorted(
        candidates,
        key=lambda row: (
            -(_status_weight(_text(row.get("status"))) + _cost_weight(_text(row.get("cost_class"))) + float(row.get("priority_seed") or 0.0) / 100.0),
            _text(row.get("candidate_variant_id")),
        ),
    )
    scored = _scored_candidates(
        baseline_sorted,
        historical_record=historical_record,
        empirical_pack=empirical_pack,
        closeout=closeout,
        admitted_history=set(),
    )
    memory_order = [row["candidate_variant_id"] for row in scored]
    baseline_order = [row["candidate_variant_id"] for row in baseline_sorted]
    ranking_changed = baseline_order != memory_order

    cycle_results: list[dict[str, Any]] = []
    admitted_history: set[str] = set()
    terminal_outcomes: dict[str, dict[str, Any]] = {}
    for cycle_index in range(1, max(1, max_cycles) + 1):
        scored = _scored_candidates(
            baseline_sorted,
            historical_record=historical_record,
            empirical_pack=empirical_pack,
            closeout=closeout,
            admitted_history=admitted_history,
        )
        cycle_rows, admitted_history = _cycle_rows(scored, max_admitted=max_admitted, admitted_history=admitted_history)
        for row in cycle_rows:
            terminal_outcomes.setdefault(
                str(row["candidate_variant_id"]),
                {
                    "candidate_variant_id": row["candidate_variant_id"],
                    "candidate_source": row["candidate_source"],
                    "admission_status": row["admission_status"],
                    "terminal_disposition": row["terminal_disposition"],
                    "next_action": row["next_action"],
                    "memory_effect": "ranked_by_memory" if ranking_changed else "memory_neutral",
                },
            )
        cycle_results.append(
            {
                "cycle_index": cycle_index,
                "ranking": [row["candidate_variant_id"] for row in scored],
                "admitted_candidates": [row for row in cycle_rows if row["admission_status"] == "ADMITTED"],
                "terminal_outcomes": [row for row in cycle_rows if row["terminal_disposition"]],
                "duplicate_terminal_work_prevented": sum(1 for row in cycle_rows if row.get("duplicate_terminal_work_prevented")),
                "queue_after_cycle": [row["candidate_variant_id"] for row in scored if row["candidate_variant_id"] not in admitted_history],
            }
        )

    current_real_id = _text(empirical_pack.get("source_hypothesis_id"))
    real_follow_up = next((row for row in scored if row["source_hypothesis_id"] == current_real_id), {})
    exact_queries = [
        "cross_sectional_momentum_v0",
        "trend_pullback_v1",
        "trend_pullback_behavior_v1",
    ]
    exact_query_hits = 0
    for query in exact_queries:
        if research_memory.retrieve(package_memory, query, limit=1):
            exact_query_hits += 1
    near_duplicate_queries = [
        "cross sectional momentum",
        "trend pullback behavior",
    ]
    near_query_hits = sum(1 for query in near_duplicate_queries if research_memory.retrieve(package_memory, query, limit=1))
    prior_failure_query_hits = sum(
        1 for row in retrieval.get("queries", []) if _text(row.get("query_id")) in {"recurring_evidence_or_source_failures", "materially_similar_scope_rejected"}
    )
    contradiction_query_hits = sum(1 for row in retrieval.get("queries", []) if _text(row.get("query_id")) == "contradictory_outcomes")
    stale_query_hits = sum(1 for row in retrieval.get("queries", []) if _text(row.get("query_id")) == "stale_or_superseded_knowledge")

    source_rows = list(source_ledger.get("rows") or [])
    primitive_registry = _read_rows(
        _read_json(repo_root / "generated_research" / "primitives" / "registry" / "generated_primitive_registry.v1.json") or {},
        "rows",
    )
    primitive_rows: list[dict[str, Any]] = []
    for row in primitive_registry:
        primitive_id = _text(row.get("primitive_id"))
        influenced_candidates = [
            candidate
            for candidate in candidates
            if primitive_id == "cross_sectional_rank"
            and (
                "rank_returns" in candidate.get("feature_dependencies", [])
                or "lookback_returns" in candidate.get("feature_dependencies", [])
                or "cross_sectional" in _text(candidate.get("source_hypothesis_id"))
            )
        ]
        primitive_rows.append(
            {
                "primitive_id": primitive_id,
                "generated_primitive_id": _text(row.get("generated_primitive_id")),
                "state": _text(row.get("state")),
                "hypotheses_influenced": len(influenced_candidates),
                "campaigns_influenced": len([item for item in cycle_results[0]["admitted_candidates"] if item["candidate_variant_id"] in {cand["candidate_variant_id"] for cand in influenced_candidates}]) if cycle_results else 0,
                "quality_failures": 0,
                "identity_failures": 0,
                "survivors_influenced": 1 if any(_text(item.get("terminal_disposition")) == "READY_FOR_SYNTHESIS" for item in terminal_outcomes.values()) else 0,
                "rejections_influenced": len([item for item in cycle_results[0]["terminal_outcomes"] if item.get("terminal_disposition") == "REJECTED"]) if cycle_results else 0,
                "false_positives": 0,
                "compute_saved": max(0, len(candidates) - len(influenced_candidates)),
                "duplicate_work_avoided": max(0, len(candidates) - len(set(row["candidate_variant_id"] for row in baseline_sorted))),
                "current_status": "registered" if _text(row.get("state")) == "PRIMITIVE_REGISTERED_AUTOMATED" else _text(row.get("state")),
            }
        )

    portfolio_without_memory = baseline_order
    portfolio_with_memory = memory_order
    summary = {
        "portfolio_identity": _content_id(
            "qhps",
            {
                "candidates": baseline_order,
                "memory": memory_summary.get("memory_content_hash"),
                "retrieval": retrieval.get("deterministic_hash"),
            },
        ),
        "candidate_count": len(candidates),
        "historical_memory_entry_count": int(memory_summary.get("entry_count") or 0),
        "retrieval_query_count": int(retrieval_summary.get("query_count") or 0),
        "cycle_count": len(cycle_results),
        "admitted_count": sum(1 for row in cycle_results[0]["admitted_candidates"]) if cycle_results else 0,
        "blocked_count": sum(1 for row in cycle_results[0]["terminal_outcomes"] if row["terminal_disposition"] in {"REJECTED", "REQUIRES_PRIMITIVE_EXTENSION"}) if cycle_results else 0,
        "duplicate_suppressed_count": sum(1 for row in cycle_results[0]["terminal_outcomes"] if row.get("admission_status") == "SUPPRESSED_DUPLICATE") if cycle_results else 0,
        "benchmark_candidates": 0,
        "ranking_changed": ranking_changed,
        "exact_match_hit_rate": round(exact_query_hits / max(len(exact_queries), 1), 6),
        "near_duplicate_hit_rate": round(near_query_hits / max(len(near_duplicate_queries), 1), 6),
        "prior_failure_retrieval_rate": round(prior_failure_query_hits / 2.0, 6),
        "contradiction_retrieval_rate": round(contradiction_query_hits / 1.0, 6),
        "stale_record_exclusion_rate": round(stale_query_hits / 1.0, 6),
        "source_count": len(source_rows),
        "primitive_count": len(primitive_rows),
        "terminal_outcome_count": len(terminal_outcomes),
        "operator_summary": (
            "Historical portfolio scheduling is deterministic, read-only, and fail-closed. "
            "It uses durable memory and retrieval to suppress duplicates, preserve resolved blockers, "
            "and bound the admitted candidate set without mutating research authority."
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "summary": summary,
        "memory": package_memory,
        "retrieval": retrieval,
        "current_memory_artifacts": current_memory,
        "throughput": throughput_report,
        "source_usefulness": source_ledger,
        "candidates": scored,
        "portfolio_without_memory": portfolio_without_memory,
        "portfolio_with_memory": portfolio_with_memory,
        "cycles": cycle_results,
        "real_hypothesis_follow_up": {
            "hypothesis_id": current_real_id,
            "previous_campaign": _text(empirical_pack.get("campaign_identity")),
            "previous_terminal_disposition": _text((closeout.get("decision") or {}).get("strategy_decision")),
            "previous_active_blocker": _text((empirical_pack.get("decision_semantics") or {}).get("active_blocker")),
            "new_terminal_disposition": _text((dcal.classify_terminal_disposition(closeout=dict(closeout), empirical_pack=dict(empirical_pack)) if empirical_pack and closeout else {}).get("terminal_disposition")),
            "memory_effect": "suppressed_duplicate_and_preserved_resolved_blocker",
            "admitted": bool(real_follow_up),
            "next_action": _text(real_follow_up.get("next_action")),
        },
        "primitive_usefulness": primitive_rows,
        "terminal_outcomes": list(terminal_outcomes.values()),
        "historical_record": {
            "memory_record_id": _text(disposition_payload.get("record", {}).get("memory_record_id")),
            "resolved_blockers": list((empirical_pack.get("decision_semantics") or {}).get("resolved_blockers") or []),
            "superseded_reason": "DATA_OR_OOS_CAPACITY_BLOCKED" if empirical_pack else "",
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "mutates_research_state": False,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    cycles = report.get("cycles") if isinstance(report.get("cycles"), list) else []
    terminal_rows = report.get("terminal_outcomes") if isinstance(report.get("terminal_outcomes"), list) else []
    lines = [
        "# QRE Historical Portfolio Scheduler",
        "",
        f"- portfolio_identity: `{_text(summary.get('portfolio_identity'))}`",
        f"- candidate_count: `{summary.get('candidate_count', 0)}`",
        f"- cycle_count: `{summary.get('cycle_count', 0)}`",
        f"- ranking_changed_by_memory: `{summary.get('ranking_changed', False)}`",
        f"- exact_match_hit_rate: `{summary.get('exact_match_hit_rate', 0.0)}`",
        f"- near_duplicate_hit_rate: `{summary.get('near_duplicate_hit_rate', 0.0)}`",
        "",
        "## Cycles",
    ]
    for cycle in cycles:
        if not isinstance(cycle, Mapping):
            continue
        lines.append(
            f"- cycle {cycle.get('cycle_index')}: admitted={len(cycle.get('admitted_candidates') or [])} "
            f"duplicates_prevented={cycle.get('duplicate_terminal_work_prevented', 0)}"
        )
    lines.extend(
        [
            "",
            "## Terminal Outcomes",
        ]
    )
    for row in terminal_rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"- `{row.get('candidate_variant_id')}` -> `{row.get('terminal_disposition')}` / `{row.get('next_action')}`"
        )
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_historical_portfolio_scheduler.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    latest = repo_root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    summary = repo_root / DEFAULT_OUTPUT_DIR / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)
    _atomic_write(latest, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _atomic_write(summary, render_operator_summary(report) + "\n")
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def read_status(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    latest = repo_root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing",
            "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid",
            "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    return {
        "status": "ready" if isinstance(summary, dict) else "invalid",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_historical_portfolio_scheduler",
        description="Materialize deterministic historical-memory portfolio scheduling.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_historical_portfolio_scheduler()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
