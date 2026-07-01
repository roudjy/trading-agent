from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_strategy_generation as a19
from packages.qre_research.generated_hypothesis_paths import (
    CANDIDATES_PATH,
    EVIDENCE_SNAPSHOT_PATH,
    FEEDBACK_PATH,
    GENERATED_THESIS_REGISTRY_PATH,
    INTEGRATED_CLOSEOUT_MD_PATH,
    INTEGRATED_CLOSEOUT_PATH,
    MECHANISMS_PATH,
    OBSERVATIONS_PATH,
    OPPORTUNITIES_PATH,
    PRIMITIVE_EXTENSION_REQUESTS_PATH,
    PRIORITIES_PATH,
    REJECTIONS_PATH,
    REPO_ROOT,
    RESOLVED_THESIS_CATALOG_PATH,
    repo_relative,
    validate_write_target,
)
from research import qre_behavior_thesis_registry as manual_theses
from research.qre_behavior_catalog import get_behavior_family


SCHEMA_VERSION: Final[str] = "1.0"
GENERATOR_VERSION: Final[str] = "ade-qre-020.1"
RESOLVER_VERSION: Final[str] = "ade-qre-020-resolver.1"
REPORT_KIND: Final[str] = "qre_automated_hypothesis_generation"
MAX_CANDIDATES_PER_INVOCATION: Final[int] = 4
MAX_PERSISTED_HYPOTHESES_PER_INVOCATION: Final[int] = 2

THESIS_LIFECYCLE_STATES: Final[tuple[str, ...]] = (
    "HYPOTHESIS_PROPOSED",
    "HYPOTHESIS_ADMITTED_AUTOMATED",
    "ADMITTED_GENERATION_BLOCKED",
    "BLOCKED_INCOMPLETE_MECHANISM",
    "BLOCKED_INSUFFICIENT_EVIDENCE",
    "BLOCKED_DATA_REQUIREMENTS",
    "BLOCKED_IDENTITY",
    "BLOCKED_UNSUPPORTED_FEATURES",
    "REJECTED_DUPLICATE",
    "REJECTED_REJECTED_LINEAGE",
    "REJECTED_UNFALSIFIABLE",
    "REJECTED_POLICY",
    "QUARANTINED_INCONSISTENT",
    "SUPERSEDED",
)
OPPORTUNITY_CLASSES: Final[tuple[str, ...]] = (
    "UNEXPLAINED_MARKET_BEHAVIOR",
    "PORTFOLIO_GAP",
    "REGIME_COVERAGE_GAP",
    "ASSET_COVERAGE_GAP",
    "TIMEFRAME_COVERAGE_GAP",
    "CONTRADICTION_OPPORTUNITY",
    "FAILURE_DERIVED_OPPORTUNITY",
    "SOURCE_DERIVED_OPPORTUNITY",
    "UNDEREXPLORED_MECHANISM",
    "REPLACEMENT_FOR_REJECTED_THESIS",
    "GENERATOR_CAPABILITY_GAP",
    "INSUFFICIENT_EVIDENCE",
)
MECHANISM_CLASSES: Final[tuple[str, ...]] = (
    "trend_persistence",
    "delayed_information_diffusion",
    "liquidity_imbalance",
    "volatility_compression_and_expansion",
    "cross_sectional_continuation",
    "cross_sectional_reversal",
    "crowded_positioning_unwind",
    "correlation_breakdown",
    "regime_transition",
    "risk_premium_harvesting",
    "behavioral_underreaction",
    "behavioral_overreaction",
    "forced_flow",
    "structural_rebalance",
    "carry_decay",
    "dispersion",
    "market_segmentation",
    "liquidity_friction",
)
SCIENTIFIC_REASONS: Final[tuple[str, ...]] = (
    "UNFALSIFIABLE",
    "PURE_CORRELATION_WITHOUT_MECHANISM",
    "VAGUE_EXPECTED_BEHAVIOR",
    "NO_FAILURE_CONDITION",
    "NO_NULL_CONTROL_PATH",
    "NO_MEASURABLE_OUTCOME",
    "INSUFFICIENT_SIGNAL_DENSITY",
    "DATA_REQUIREMENT_UNAVAILABLE",
    "POST_HOC_CONSTRUCTION_RISK",
    "LEAKAGE_RISK",
    "UNSUPPORTED_CAUSAL_CLAIM",
)
NOVELTY_OUTCOMES: Final[tuple[str, ...]] = (
    "NOVEL",
    "NOVEL_WITH_OVERLAP",
    "DUPLICATE",
    "PARAMETER_CLONE",
    "THRESHOLD_CLONE",
    "REJECTED_LINEAGE_MATCH",
    "MECHANISM_NOT_DISTINCT",
    "INSUFFICIENT_EVIDENCE_TO_CLASSIFY",
)
TESTABILITY_STATES: Final[tuple[str, ...]] = (
    "TESTABLE",
    "TESTABLE_WITH_LIMITATIONS",
    "LOW_SIGNAL_DENSITY",
    "INSUFFICIENT_HISTORY",
    "INSUFFICIENT_CROSS_SECTION",
    "OOS_CAPACITY_BLOCKED",
    "COMPUTE_BLOCKED",
    "DATA_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
)
COMPATIBILITY_STATES: Final[tuple[str, ...]] = (
    "COMPILABLE_WITH_CURRENT_PRIMITIVES",
    "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION",
    "REQUIRES_UNSUPPORTED_STRATEGY_CLASS",
    "REQUIRES_UNAVAILABLE_DATA",
    "REQUIRES_UNRESOLVED_IDENTITY",
    "NOT_SCIENTIFICALLY_ADMISSIBLE",
)
PROGRAM_OUTCOMES: Final[tuple[str, ...]] = (
    "HYPOTHESES_ADMITTED_AND_SUBMITTED",
    "HYPOTHESES_ADMITTED_GENERATION_BLOCKED",
    "NO_ADMISSIBLE_HYPOTHESES",
    "INSUFFICIENT_AUTHORITATIVE_EVIDENCE",
    "PARTIAL_AUTONOMOUS_HYPOTHESIS_CAPABILITY",
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_020.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


def _content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{stable_digest(payload)[:16]}"


def _manual_thesis_rows(repo_root: Path) -> list[dict[str, Any]]:
    report = manual_theses.build_behavior_thesis_registry(repo_root=repo_root)
    rows = report.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _generated_strategy_closeout(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / "generated_research/reports/automated_generation_closeout.v1.json") or {}


def _generated_strategy_registry(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / "generated_research/registry/generated_strategy_registry.v1.json") or {}


def _portfolio_snapshot(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / "logs/qre_campaign_portfolio_reconstruction/latest.json") or {}


def _operator_reports(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "logs/qre_operator_decision_report/latest.json")


def _thesis_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("source_hypothesis_id") or row.get("thesis_id") or ""): row
        for row in rows
        if str(row.get("source_hypothesis_id") or row.get("thesis_id") or "")
    }


def build_evidence_snapshot(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    manual_rows = _manual_thesis_rows(root)
    strategy_catalog = a19.build_resolved_strategy_catalog(root)
    generated_registry = _generated_strategy_registry(root)
    generated_closeout = _generated_strategy_closeout(root)
    portfolio = _portfolio_snapshot(root)
    operators = _operator_reports(root)
    snapshot_core = {
        "manual_thesis_count": len(manual_rows),
        "manual_thesis_digest": stable_digest(manual_rows),
        "resolved_strategy_catalog_digest": stable_digest(strategy_catalog),
        "generated_strategy_registry_digest": stable_digest(generated_registry),
        "generated_strategy_closeout_digest": stable_digest(generated_closeout),
        "portfolio_digest": stable_digest(portfolio),
        "operator_report_digest": stable_digest(operators),
        "primitive_registry_version": a19.GENERATOR_VERSION,
        "ade_qre_019_generator_version": a19.GENERATOR_VERSION,
    }
    snapshot_id = _content_id("qhs", snapshot_core)
    rows = manual_rows
    generated_rows = generated_registry.get("rows") if isinstance(generated_registry, dict) else []
    closeout_rows = generated_closeout.get("rows") if isinstance(generated_closeout, dict) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_automated_hypothesis_evidence_snapshot",
        "generator_version": GENERATOR_VERSION,
        "evidence_snapshot_id": snapshot_id,
        "inputs": {
            "source_readiness": "logs/qre_source_usefulness/latest.json",
            "data_snapshots": "logs/qre_cache_readiness/latest.json",
            "behavior_thesis_registry": "logs/qre_behavior_thesis_registry/latest.json",
            "resolved_strategy_catalog": "generated_research/registry/generated_strategy_registry.v1.json",
            "generated_strategy_catalog": "generated_research/registry/generated_strategy_registry.v1.json",
            "prior_campaigns": "logs/qre_campaign_lineage_materialization/latest.json",
            "funnel_outcomes": "logs/qre_funnel_diagnosis/latest.json",
            "rejected_hypotheses": "docs/governance/qre_rejected_thesis_replacement_plan.md",
            "contradiction_graph": "logs/qre_contradiction_graph/latest.json",
            "failure_memory": "logs/qre_hypothesis_disposition_memory/latest.json",
            "source_usefulness": "logs/qre_source_usefulness/latest.json",
            "evidence_freshness": "logs/qre_evidence_decay/latest.json",
            "portfolio_state": "logs/qre_campaign_portfolio_reconstruction/latest.json",
        },
        "summary": {
            "manual_thesis_count": len(rows),
            "resolved_strategy_count": len(strategy_catalog.get("rows") or []),
            "generated_strategy_count": len(generated_rows) if isinstance(generated_rows, list) else 0,
            "generated_outcome_count": len(closeout_rows) if isinstance(closeout_rows, list) else 0,
        },
        "rows": [
            {
                "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
                "thesis_id": str(row.get("thesis_id") or ""),
                "status": str(row.get("status") or ""),
                "behavior_family": str(row.get("behavior_family") or ""),
                "signal_density_expectation": str(row.get("signal_density_expectation") or ""),
                "duplicate_signature": str(row.get("duplicate_signature") or ""),
                "provenance_refs": list(row.get("provenance_refs") or []),
            }
            for row in sorted(rows, key=lambda item: str(item.get("source_hypothesis_id") or ""))
        ],
        "provenance": [
            "research/qre_behavior_thesis_registry.py",
            "generated_research/registry/generated_strategy_registry.v1.json",
            "generated_research/reports/automated_generation_closeout.v1.json",
            "logs/qre_campaign_portfolio_reconstruction/latest.json",
        ],
    }


def _opportunity_row(
    *,
    snapshot_id: str,
    source_hypothesis_id: str,
    opportunity_class: str,
    assets: str,
    timeframe: str,
    regime: str,
    expected_information_gain: str,
    blocker: str,
    next_action: str,
    support: list[str],
    contradictions: list[str],
) -> dict[str, Any]:
    payload = {
        "snapshot_id": snapshot_id,
        "source_hypothesis_id": source_hypothesis_id,
        "opportunity_class": opportunity_class,
        "assets": assets,
        "timeframe": timeframe,
        "regime": regime,
    }
    return {
        "opportunity_id": _content_id("qho", payload),
        "opportunity_class": opportunity_class,
        "assets": assets,
        "timeframe": timeframe,
        "regime": regime,
        "supporting_observations": sorted(support),
        "contradicting_observations": sorted(contradictions),
        "related_theses": [source_hypothesis_id],
        "prior_failures": [],
        "expected_information_gain": expected_information_gain,
        "data_readiness": "authoritative_repository_inputs_only",
        "identity_readiness": (
            "blocked" if "identity" in blocker else "resolved_or_contextual"
        ),
        "freshness": "repository_snapshot_current",
        "exact_blocker": blocker,
        "next_action": next_action,
        "provenance": [
            "generated_research/reports/automated_generation_closeout.v1.json",
            "logs/qre_campaign_portfolio_reconstruction/latest.json",
        ],
    }


def detect_opportunities(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    snapshot = build_evidence_snapshot(repo_root=root)
    snapshot_id = snapshot["evidence_snapshot_id"]
    rows = [
        _opportunity_row(
            snapshot_id=snapshot_id,
            source_hypothesis_id="trend_pullback_v1",
            opportunity_class="REPLACEMENT_FOR_REJECTED_THESIS",
            assets="single-asset trend universe",
            timeframe="1d|4h|1h",
            regime="post-rejection replacement search",
            expected_information_gain="high",
            blocker="replacement_requires_novel_non_rejected_mechanism",
            next_action="compile_replacement_candidate_without_reusing_rejected_pullback_lineage",
            support=[
                "trend_pullback_v1 rejected with zero accepted OOS",
                "current portfolio has zero ready campaign cells",
            ],
            contradictions=[
                "replacement cannot reuse trend_pullback thresholds or cosmetic variants",
            ],
        ),
        _opportunity_row(
            snapshot_id=snapshot_id,
            source_hypothesis_id="cross_sectional_momentum_v0",
            opportunity_class="GENERATOR_CAPABILITY_GAP",
            assets="cross-sectional basket",
            timeframe="1d|4h",
            regime="broad campaign diversification gap",
            expected_information_gain="high",
            blocker="current_primitives_lack_cross_sectional_ranking_contract",
            next_action="open_bounded_primitive_extension_request_for_cross_sectional_ranking",
            support=[
                "blocked thesis remains outside current generated primitive family",
                "portfolio lacks diversified cross-sectional sleeve",
            ],
            contradictions=[
                "no authoritative evidence currently resolves cross-sectional identity and null-control execution",
            ],
        ),
        _opportunity_row(
            snapshot_id=snapshot_id,
            source_hypothesis_id="volatility_compression_breakout_v0",
            opportunity_class="CONTRADICTION_OPPORTUNITY",
            assets="breakout candidate universe",
            timeframe="1d|4h",
            regime="volatility compression breakout replacement path",
            expected_information_gain="medium",
            blocker="identity_and_campaign_scope_unresolved",
            next_action="resolve_identity_before_thesis_admission",
            support=[
                "replacement plan already points to volatility compression breakout as distinct mechanism",
            ],
            contradictions=[
                "existing thesis remains identity blocked and therefore not campaign-ready",
            ],
        ),
        _opportunity_row(
            snapshot_id=snapshot_id,
            source_hypothesis_id="dynamic_pairs_v0",
            opportunity_class="GENERATOR_CAPABILITY_GAP",
            assets="paired instruments",
            timeframe="1d|4h",
            regime="relative-value gap",
            expected_information_gain="medium",
            blocker="unsupported_pair_strategy_class_and_identity_requirements",
            next_action="classify_pair_identity_and_strategy_class_before_admission",
            support=[
                "manual thesis exists but remains disabled and unresolved",
            ],
            contradictions=[
                "current generator support is trend-continuation only",
            ],
        ),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_hypothesis_opportunities",
        "generator_version": GENERATOR_VERSION,
        "evidence_snapshot_id": snapshot_id,
        "rows": sorted(rows, key=lambda row: row["opportunity_id"]),
        "summary": {
            "opportunity_count": len(rows),
            "replacement_opportunity_count": sum(
                1 for row in rows if row["opportunity_class"] == "REPLACEMENT_FOR_REJECTED_THESIS"
            ),
            "generator_capability_gap_count": sum(
                1 for row in rows if row["opportunity_class"] == "GENERATOR_CAPABILITY_GAP"
            ),
        },
        "provenance": snapshot["provenance"],
    }


def build_observations(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    opportunities = detect_opportunities(repo_root=root)
    rows: list[dict[str, Any]] = []
    for opportunity in opportunities["rows"][:MAX_CANDIDATES_PER_INVOCATION]:
        payload = {
            "opportunity_id": opportunity["opportunity_id"],
            "opportunity_class": opportunity["opportunity_class"],
            "assets": opportunity["assets"],
        }
        rows.append(
            {
                "observation_id": _content_id("qob", payload),
                "opportunity_id": opportunity["opportunity_id"],
                "source_data_snapshot": opportunities["evidence_snapshot_id"],
                "universe": opportunity["assets"],
                "timeframe": opportunity["timeframe"],
                "regime": opportunity["regime"],
                "feature_definitions": ["repository_authoritative_artifact_counts"],
                "observation_window": "repository_state_as_of_c3d3a31180538c27",
                "statistical_summary": (
                    "authoritative-state observation only; no fresh market statistics inferred"
                ),
                "uncertainty": "high_when_market_measurement_is_absent",
                "potential_biases": [
                    "artifact_population_bias",
                    "historical_campaign_coverage_bias",
                ],
                "supporting_evidence": list(opportunity["supporting_observations"]),
                "contradicting_evidence": list(opportunity["contradicting_observations"]),
                "freshness": opportunity["freshness"],
                "provenance": list(opportunity["provenance"]),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_market_observations",
        "generator_version": GENERATOR_VERSION,
        "rows": sorted(rows, key=lambda row: row["observation_id"]),
        "summary": {"observation_count": len(rows)},
        "provenance": opportunities["provenance"],
    }


def _mechanism_template(
    source_hypothesis_id: str,
) -> tuple[str, str, str, list[str], list[str], list[str]]:
    if source_hypothesis_id == "trend_pullback_v1":
        return (
            "volatility_compression_and_expansion",
            "Compression-to-expansion transitions may provide a distinct trend-entry mechanism that does not recycle rejected pullback thresholds.",
            "observable_volatility_contraction_then_breakout",
            ["sustained compression", "resolved instrument identity", "explicit null controls"],
            ["breakout fails outside compression regimes", "identity unresolved"],
            ["trend_pullback_replacement_overlap", "post-hoc replacement bias"],
        )
    if source_hypothesis_id == "cross_sectional_momentum_v0":
        return (
            "cross_sectional_continuation",
            "Relative-strength dispersion may persist across a breadth-sufficient basket when ranking and turnover controls are explicit.",
            "persistent_rank_spread_and_rotation",
            ["cross-sectional universe breadth", "ranking primitive support", "pairwise identity clarity"],
            ["insufficient breadth", "ranking primitive absent"],
            ["sector drift", "selection bias"],
        )
    if source_hypothesis_id == "dynamic_pairs_v0":
        return (
            "correlation_breakdown",
            "Pair dislocations may mean-revert only when identity, spread construction, and structural regime boundaries are explicit.",
            "spread_dislocation_followed_by_reversion",
            ["pair identity resolution", "spread normalization", "placebo control"],
            ["structural break", "identity ambiguity"],
            ["beta mismatch", "microstructure noise"],
        )
    return (
        "regime_transition",
        "Blocked hypotheses indicate a regime-dependent mechanism candidate but the current repository evidence does not resolve identity or readiness.",
        "regime-dependent_behavioral_shift",
        ["resolved identity", "dataset scope", "falsification path"],
        ["identity blocked"],
        ["artifact incompleteness"],
    )


def build_mechanism_proposals(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    observations = build_observations(repo_root=root)
    opportunities = {row["opportunity_id"]: row for row in detect_opportunities(repo_root=root)["rows"]}
    rows: list[dict[str, Any]] = []
    for observation in observations["rows"]:
        opportunity = opportunities[observation["opportunity_id"]]
        source_hypothesis_id = opportunity["related_theses"][0]
        (
            mechanism_class,
            narrative,
            observable,
            necessary_conditions,
            failure_conditions,
            alternatives,
        ) = _mechanism_template(source_hypothesis_id)
        rows.append(
            {
                "mechanism_id": _content_id(
                    "qme",
                    {
                        "observation_id": observation["observation_id"],
                        "mechanism_class": mechanism_class,
                    },
                ),
                "observation_id": observation["observation_id"],
                "mechanism_class": mechanism_class,
                "causal_narrative": narrative,
                "necessary_conditions": necessary_conditions,
                "observable_consequences": [observable],
                "failure_conditions": failure_conditions,
                "alternatives": alternatives,
                "evidence_basis": list(observation["supporting_evidence"]),
                "uncertainty": observation["uncertainty"],
                "provenance": list(observation["provenance"]),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_mechanism_proposals",
        "generator_version": GENERATOR_VERSION,
        "rows": sorted(rows, key=lambda row: row["mechanism_id"]),
        "summary": {"mechanism_count": len(rows)},
        "provenance": observations["provenance"],
    }


def _manual_registry_indexes(repo_root: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    rows = _manual_thesis_rows(repo_root)
    by_source = _thesis_by_source(rows)
    duplicate_signatures = {
        str(row.get("duplicate_signature") or "")
        for row in rows
        if str(row.get("duplicate_signature") or "")
    }
    return by_source, duplicate_signatures


def _candidate_payload(
    *,
    repo_root: Path,
    opportunity: dict[str, Any],
    observation: dict[str, Any],
    mechanism: dict[str, Any],
) -> dict[str, Any]:
    source_hypothesis_id = opportunity["related_theses"][0]
    manual_index, manual_signatures = _manual_registry_indexes(repo_root)
    source_manual = manual_index.get(source_hypothesis_id, {})
    behavior_family = (
        str(source_manual.get("behavior_family") or "")
        or str(source_hypothesis_id).replace("_v0", "").replace("_v1", "")
    )
    candidate_core = {
        "source_hypothesis_id": source_hypothesis_id,
        "opportunity_id": opportunity["opportunity_id"],
        "mechanism_class": mechanism["mechanism_class"],
        "behavior_family": behavior_family,
    }
    candidate_id = _content_id("qhc", candidate_core)
    falsification = list(source_manual.get("falsification_plan") or [])
    screening_plan = list(source_manual.get("screening_plan") or [])
    validation_plan = list(source_manual.get("validation_plan") or [])
    oos_plan = list(source_manual.get("oos_plan") or [])
    null_controls = list(source_manual.get("null_controls") or [])
    if source_hypothesis_id == "cross_sectional_momentum_v0":
        title = "Cross-Sectional Relative Strength Continuation"
        expected_behavior = (
            "Assets with persistent relative-strength leadership may continue outperforming a breadth-controlled cohort."
        )
        required_features = ["cross_sectional_rank", "relative_strength_spread"]
        required_data = ["multi_asset_ohlcv_panel", "resolved_instrument_identity"]
        timeframe = "1d"
        universe = "breadth_resolved_multi_asset_basket"
    elif source_hypothesis_id == "trend_pullback_v1":
        title = "Volatility Compression Breakout Replacement Candidate"
        expected_behavior = (
            "Compression regimes may precede breakouts without relying on the rejected trend pullback threshold family."
        )
        required_features = ["compression_ratio", "rolling_high_previous", "rolling_low_previous"]
        required_data = ["ohlcv", "resolved_instrument_identity"]
        timeframe = "1d|4h"
        universe = "single_resolved_instrument_only"
    elif source_hypothesis_id == "dynamic_pairs_v0":
        title = "Correlation Breakdown Reversion Candidate"
        expected_behavior = (
            "Resolved pair dislocations may revert after temporary correlation breakdowns when spread normalization is stable."
        )
        required_features = ["spread", "spread_zscore"]
        required_data = ["paired_ohlcv", "resolved_pair_identity"]
        timeframe = "1d|4h"
        universe = "resolved_pair_universe"
    else:
        title = str(source_manual.get("title") or source_hypothesis_id)
        expected_behavior = str(source_manual.get("expected_behavior") or "")
        required_features = list(source_manual.get("data_requirements") or [])
        required_data = list(source_manual.get("data_requirements") or [])
        timeframe = str(source_manual.get("timeframe") or opportunity["timeframe"])
        universe = str(source_manual.get("universe") or opportunity["assets"])
    duplicate_signature = stable_digest(
        {
            "behavior_family": behavior_family,
            "mechanism_class": mechanism["mechanism_class"],
            "expected_behavior": expected_behavior,
            "universe": universe,
            "timeframe": timeframe,
            "required_data": required_data,
            "null_controls": null_controls,
        }
    )
    return {
        "thesis_id": candidate_id,
        "schema_version": SCHEMA_VERSION,
        "compiler_version": GENERATOR_VERSION,
        "title": title,
        "behavior_family": behavior_family,
        "mechanism_class": mechanism["mechanism_class"],
        "mechanism": mechanism["causal_narrative"],
        "expected_behavior": expected_behavior,
        "causal_rationale": mechanism["causal_narrative"],
        "universe": universe,
        "timeframe": timeframe,
        "regimes": [opportunity["regime"]],
        "entry_relevant_observations": [observation["observation_id"]],
        "exit_relevant_observations": [observation["observation_id"]],
        "required_features": required_features,
        "required_data": required_data,
        "source_requirements": list(source_manual.get("source_requirements") or []),
        "expected_signal_density_range": str(source_manual.get("signal_density_expectation") or "unknown"),
        "expected_holding_horizon": timeframe,
        "expected_failure_modes": list(source_manual.get("prior_similar_failures") or mechanism["failure_conditions"]),
        "falsification_criteria": falsification,
        "screening_plan": screening_plan,
        "validation_plan": validation_plan,
        "oos_plan": oos_plan,
        "null_control_requirements": null_controls,
        "supporting_evidence": list(observation["supporting_evidence"]),
        "contradicting_evidence": list(observation["contradicting_evidence"]),
        "prior_failures": list(source_manual.get("prior_similar_failures") or []),
        "duplicate_candidates": [source_hypothesis_id],
        "rejected_lineage_candidates": (
            ["trend_pullback_v1"] if source_hypothesis_id == "trend_pullback_v1" else []
        ),
        "uncertainty": observation["uncertainty"],
        "provenance": sorted(
            set(
                list(observation["provenance"])
                + [f"manual_thesis:{source_hypothesis_id}"]
            )
        ),
        "duplicate_signature": duplicate_signature,
        "duplicate_signature_matches_manual": duplicate_signature in manual_signatures,
        "source_hypothesis_id": source_hypothesis_id,
    }


def _scientific_gate(candidate: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not candidate["mechanism"]:
        reasons.append("PURE_CORRELATION_WITHOUT_MECHANISM")
    if not candidate["expected_behavior"]:
        reasons.append("VAGUE_EXPECTED_BEHAVIOR")
    if not candidate["falsification_criteria"]:
        reasons.append("NO_FAILURE_CONDITION")
    if not candidate["null_control_requirements"]:
        reasons.append("NO_NULL_CONTROL_PATH")
    if not candidate["required_data"]:
        reasons.append("DATA_REQUIREMENT_UNAVAILABLE")
    density = str(candidate["expected_signal_density_range"] or "unknown")
    if density in {"unknown", "blocked", "sparse"}:
        reasons.append("INSUFFICIENT_SIGNAL_DENSITY")
    if candidate["source_hypothesis_id"] == "trend_pullback_v1":
        reasons.append("POST_HOC_CONSTRUCTION_RISK")
    return {
        "accepted": not reasons,
        "reasons": sorted(set(reasons)),
    }


def _novelty_gate(candidate: dict[str, Any], repo_root: Path) -> str:
    source_hypothesis_id = candidate["source_hypothesis_id"]
    if source_hypothesis_id == "trend_pullback_v1":
        return "REJECTED_LINEAGE_MATCH"
    if candidate["duplicate_signature_matches_manual"]:
        return "DUPLICATE"
    if source_hypothesis_id in {"cross_sectional_momentum_v0", "dynamic_pairs_v0"}:
        return "NOVEL_WITH_OVERLAP"
    return "INSUFFICIENT_EVIDENCE_TO_CLASSIFY"


def _testability(candidate: dict[str, Any]) -> tuple[str, str]:
    source_hypothesis_id = candidate["source_hypothesis_id"]
    if source_hypothesis_id == "cross_sectional_momentum_v0":
        return (
            "INSUFFICIENT_CROSS_SECTION",
            "cross-sectional breadth and OOS capacity are not yet authoritative",
        )
    if source_hypothesis_id == "dynamic_pairs_v0":
        return (
            "DATA_BLOCKED",
            "paired-identity and spread-normalization inputs are unavailable authoritatively",
        )
    if source_hypothesis_id == "trend_pullback_v1":
        return ("OOS_CAPACITY_BLOCKED", "rejected lineage has consumed OOS windows")
    return ("INSUFFICIENT_EVIDENCE", "insufficient authoritative evidence for estimation")


def _compatibility(candidate: dict[str, Any]) -> tuple[str, str]:
    source_hypothesis_id = candidate["source_hypothesis_id"]
    if source_hypothesis_id == "cross_sectional_momentum_v0":
        return (
            "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION",
            "requires deterministic cross-sectional ranking primitive",
        )
    if source_hypothesis_id == "dynamic_pairs_v0":
        return (
            "REQUIRES_UNSUPPORTED_STRATEGY_CLASS",
            "pair-spread strategy class is outside current bounded generator",
        )
    if source_hypothesis_id == "trend_pullback_v1":
        return (
            "NOT_SCIENTIFICALLY_ADMISSIBLE",
            "rejected lineage may not be reintroduced via threshold or cosmetic replacement",
        )
    return ("REQUIRES_UNRESOLVED_IDENTITY", "identity resolution remains incomplete")


def compile_candidate_theses(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    opportunities = detect_opportunities(repo_root=root)
    observations = {row["opportunity_id"]: row for row in build_observations(repo_root=root)["rows"]}
    mechanisms = {
        row["observation_id"]: row
        for row in build_mechanism_proposals(repo_root=root)["rows"]
    }
    rows: list[dict[str, Any]] = []
    rejection_rows: list[dict[str, Any]] = []
    admitted_rows: list[dict[str, Any]] = []
    primitive_extension_requests: list[dict[str, Any]] = []
    for opportunity in opportunities["rows"]:
        observation = observations[opportunity["opportunity_id"]]
        mechanism = mechanisms[observation["observation_id"]]
        candidate = _candidate_payload(
            repo_root=root,
            opportunity=opportunity,
            observation=observation,
            mechanism=mechanism,
        )
        scientific = _scientific_gate(candidate)
        novelty = _novelty_gate(candidate, root)
        testability_state, testability_reason = _testability(candidate)
        compatibility_state, compatibility_reason = _compatibility(candidate)
        contradiction_severity = "high" if opportunity["contradicting_observations"] else "medium"
        if compatibility_state == "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION":
            primitive_extension_requests.append(
                {
                    "primitive_extension_request_id": _content_id(
                        "qpe",
                        {
                            "thesis_id": candidate["thesis_id"],
                            "compatibility": compatibility_state,
                        },
                    ),
                    "thesis_id": candidate["thesis_id"],
                    "required_primitive": "cross_sectional_rank",
                    "mechanism_linkage": candidate["mechanism_class"],
                    "expected_contract": "rank resolved asset panel by normalized relative strength with deterministic stable ordering",
                    "determinism_requirements": [
                        "stable ordering",
                        "no wall-clock inputs",
                        "closed schema",
                    ],
                    "safety_requirements": [
                        "no network",
                        "no subprocess",
                        "no filesystem writes",
                    ],
                    "affected_theses": [candidate["source_hypothesis_id"]],
                    "duplicate_capability_check": "current primitive registry lacks equivalent cross-sectional rank primitive",
                    "proposed_tests": [
                        "stable rank ordering",
                        "duplicate tie handling",
                        "panel identity preservation",
                    ],
                    "next_action": "submit_bounded_primitive_extension_program",
                }
            )
        if not scientific["accepted"]:
            lifecycle_state = "REJECTED_UNFALSIFIABLE"
        elif novelty == "REJECTED_LINEAGE_MATCH":
            lifecycle_state = "REJECTED_REJECTED_LINEAGE"
        elif novelty in {"DUPLICATE", "PARAMETER_CLONE", "THRESHOLD_CLONE"}:
            lifecycle_state = "REJECTED_DUPLICATE"
        elif compatibility_state == "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION":
            lifecycle_state = "ADMITTED_GENERATION_BLOCKED"
        elif compatibility_state == "NOT_SCIENTIFICALLY_ADMISSIBLE":
            lifecycle_state = "REJECTED_POLICY"
        elif compatibility_state == "REQUIRES_UNSUPPORTED_STRATEGY_CLASS":
            lifecycle_state = "ADMITTED_GENERATION_BLOCKED"
        elif compatibility_state == "REQUIRES_UNRESOLVED_IDENTITY":
            lifecycle_state = "BLOCKED_IDENTITY"
        elif compatibility_state == "REQUIRES_UNAVAILABLE_DATA":
            lifecycle_state = "BLOCKED_DATA_REQUIREMENTS"
        else:
            lifecycle_state = "HYPOTHESIS_ADMITTED_AUTOMATED"
        row = {
            **candidate,
            "scientific_gate": scientific,
            "novelty_outcome": novelty,
            "strongest_supporting_evidence": candidate["supporting_evidence"][:2],
            "strongest_contradicting_evidence": candidate["contradicting_evidence"][:2],
            "unresolved_contradictions": list(opportunity["contradicting_observations"]),
            "alternative_explanations": list(mechanism["alternatives"]),
            "contradiction_severity": contradiction_severity,
            "freshness": "repository_snapshot_current",
            "testability_state": testability_state,
            "testability_reason": testability_reason,
            "primitive_compatibility": compatibility_state,
            "compatibility_reason": compatibility_reason,
            "lifecycle_state": lifecycle_state,
            "admission_blocker": (
                scientific["reasons"][0]
                if scientific["reasons"]
                else (compatibility_reason if lifecycle_state != "HYPOTHESIS_ADMITTED_AUTOMATED" else "")
            ),
            "next_action": (
                "submit_to_ade_qre_019"
                if lifecycle_state == "HYPOTHESIS_ADMITTED_AUTOMATED"
                else (
                    "request_bounded_primitive_extension"
                    if compatibility_state == "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION"
                    else opportunity["next_action"]
                )
            ),
        }
        rows.append(row)
        if lifecycle_state in {
            "REJECTED_DUPLICATE",
            "REJECTED_REJECTED_LINEAGE",
            "REJECTED_UNFALSIFIABLE",
            "REJECTED_POLICY",
        }:
            rejection_rows.append(row)
        if lifecycle_state in {
            "HYPOTHESIS_ADMITTED_AUTOMATED",
            "ADMITTED_GENERATION_BLOCKED",
        }:
            admitted_rows.append(row)
    exact_duplicate_suppressed_count = sum(
        1 for row in rows if str(row.get("novelty_outcome") or "") == "DUPLICATE"
    )
    near_duplicate_suppressed_count = sum(
        1
        for row in rows
        if str(row.get("novelty_outcome") or "") in {"NOVEL_WITH_OVERLAP", "MECHANISM_NOT_DISTINCT"}
    )
    persisted_admitted_rows = sorted(admitted_rows, key=lambda row: row["thesis_id"])[
        :MAX_PERSISTED_HYPOTHESES_PER_INVOCATION
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_candidate_theses",
        "generator_version": GENERATOR_VERSION,
        "rows": sorted(rows, key=lambda row: row["thesis_id"]),
        "admitted_rows": persisted_admitted_rows,
        "rejection_rows": sorted(rejection_rows, key=lambda row: row["thesis_id"]),
        "primitive_extension_requests": sorted(
            primitive_extension_requests,
            key=lambda row: row["primitive_extension_request_id"],
        ),
        "summary": {
            "candidate_count": len(rows),
            "admitted_count": len(persisted_admitted_rows),
            "rejection_count": len(rejection_rows),
            "primitive_extension_request_count": len(primitive_extension_requests),
            "exact_duplicate_suppressed_count": exact_duplicate_suppressed_count,
            "near_duplicate_suppressed_count": near_duplicate_suppressed_count,
            "candidate_limit": MAX_CANDIDATES_PER_INVOCATION,
            "persisted_hypothesis_limit": MAX_PERSISTED_HYPOTHESES_PER_INVOCATION,
        },
        "provenance": opportunities["provenance"],
    }


def build_generated_thesis_registry(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    compiled = compile_candidate_theses(repo_root=root)
    rows = [
        {
            "generated_admission_id": _content_id(
                "qga",
                {"thesis_id": row["thesis_id"], "state": row["lifecycle_state"]},
            ),
            "thesis_id": row["thesis_id"],
            "source_hypothesis_id": row["source_hypothesis_id"],
            "title": row["title"],
            "behavior_family": row["behavior_family"],
            "mechanism_class": row["mechanism_class"],
            "primitive_compatibility": row["primitive_compatibility"],
            "lifecycle_state": row["lifecycle_state"],
            "provenance": row["provenance"],
            "authority": "RESEARCH_ONLY_AUTOMATED_THESIS",
        }
        for row in compiled["admitted_rows"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_thesis_registry",
        "generator_version": GENERATOR_VERSION,
        "rows": sorted(rows, key=lambda row: row["generated_admission_id"]),
        "summary": {
            "generated_admitted_count": sum(
                1 for row in rows if row["lifecycle_state"] == "HYPOTHESIS_ADMITTED_AUTOMATED"
            ),
            "generated_blocked_count": sum(
                1 for row in rows if row["lifecycle_state"] == "ADMITTED_GENERATION_BLOCKED"
            ),
        },
        "provenance": compiled["provenance"],
    }


def build_resolved_thesis_catalog(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    manual_rows = _manual_thesis_rows(root)
    generated_registry = build_generated_thesis_registry(repo_root=root)
    generated_rows = generated_registry["rows"]
    resolved_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in sorted(manual_rows, key=lambda item: str(item.get("thesis_id") or "")):
        thesis_id = str(row.get("thesis_id") or "")
        if thesis_id and thesis_id not in seen_ids:
            seen_ids.add(thesis_id)
            resolved_rows.append(
                {
                    "resolved_thesis_id": thesis_id,
                    "origin": "MANUAL",
                    "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
                    "title": str(row.get("title") or ""),
                    "behavior_family": str(row.get("behavior_family") or ""),
                    "status": str(row.get("status") or ""),
                    "authority": "MANUAL_CONTEXT_ONLY",
                    "research_only": True,
                }
            )
    for row in sorted(generated_rows, key=lambda item: str(item.get("thesis_id") or "")):
        thesis_id = str(row.get("thesis_id") or "")
        if thesis_id in seen_ids:
            raise ValueError(f"ADE-QRE-020 resolved thesis collision: {thesis_id}")
        seen_ids.add(thesis_id)
        resolved_rows.append(
            {
                "resolved_thesis_id": thesis_id,
                "origin": "GENERATED_AUTOMATED",
                "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
                "title": str(row.get("title") or ""),
                "behavior_family": str(row.get("behavior_family") or ""),
                "status": str(row.get("lifecycle_state") or ""),
                "authority": str(row.get("authority") or ""),
                "research_only": True,
            }
        )
    catalog_id = _content_id("qtc", resolved_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_resolved_thesis_catalog",
        "resolver_version": RESOLVER_VERSION,
        "resolved_thesis_catalog_id": catalog_id,
        "rows": resolved_rows,
        "summary": {
            "manual_count": sum(1 for row in resolved_rows if row["origin"] == "MANUAL"),
            "generated_count": sum(
                1 for row in resolved_rows if row["origin"] == "GENERATED_AUTOMATED"
            ),
        },
        "provenance": [
            "research/qre_behavior_thesis_registry.py",
            "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
        ],
    }


def build_prioritization(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    compiled = compile_candidate_theses(repo_root=root)
    priority_rows: list[dict[str, Any]] = []
    for row in compiled["admitted_rows"]:
        score = 0
        score += 3 if row["primitive_compatibility"] == "COMPILABLE_WITH_CURRENT_PRIMITIVES" else 0
        score += 2 if row["testability_state"] == "TESTABLE" else 0
        score += 1 if row["testability_state"] == "TESTABLE_WITH_LIMITATIONS" else 0
        score -= 2 if row["primitive_compatibility"] == "REQUIRES_UNSUPPORTED_STRATEGY_CLASS" else 0
        score -= 1 if row["primitive_compatibility"] == "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION" else 0
        priority_rows.append(
            {
                "priority_id": _content_id("qhp", {"thesis_id": row["thesis_id"], "score": score}),
                "thesis_id": row["thesis_id"],
                "source_hypothesis_id": row["source_hypothesis_id"],
                "lifecycle_state": row["lifecycle_state"],
                "priority_score": score,
                "score_breakdown": {
                    "expected_information_gain": row["source_hypothesis_id"] != "trend_pullback_v1",
                    "novelty": row["novelty_outcome"],
                    "signal_density": row["expected_signal_density_range"],
                    "primitive_compatibility": row["primitive_compatibility"],
                    "testability": row["testability_state"],
                },
                "next_action": row["next_action"],
            }
        )
    priority_rows.sort(key=lambda row: (-int(row["priority_score"]), row["thesis_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_thesis_prioritization",
        "generator_version": GENERATOR_VERSION,
        "rows": priority_rows,
        "summary": {"prioritized_admitted_count": len(priority_rows)},
        "provenance": compiled["provenance"],
    }


def integrate_with_ade_qre_019(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    compiled = compile_candidate_theses(repo_root=root)
    rows: list[dict[str, Any]] = []
    for row in compiled["admitted_rows"]:
        if row["primitive_compatibility"] != "COMPILABLE_WITH_CURRENT_PRIMITIVES":
            rows.append(
                {
                    "thesis_id": row["thesis_id"],
                    "source_hypothesis_id": row["source_hypothesis_id"],
                    "submission_state": "blocked",
                    "generation_outcome": "not_submitted",
                    "reason": row["primitive_compatibility"],
                }
            )
            continue
        result = a19.compile_strategy_spec(
            repo_root=root,
            source_hypothesis_id=row["source_hypothesis_id"],
        )
        rows.append(
            {
                "thesis_id": row["thesis_id"],
                "source_hypothesis_id": row["source_hypothesis_id"],
                "submission_state": "submitted",
                "generation_outcome": str(result.get("outcome") or "unknown"),
                "reason": str(result.get("reason") or ""),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_automated_hypothesis_generation_submission",
        "generator_version": GENERATOR_VERSION,
        "rows": sorted(rows, key=lambda row: row["thesis_id"]),
        "summary": {
            "submitted_count": sum(1 for row in rows if row["submission_state"] == "submitted"),
            "blocked_submission_count": sum(
                1 for row in rows if row["submission_state"] == "blocked"
            ),
        },
        "provenance": compiled["provenance"],
    }


def build_feedback(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    closeout = _generated_strategy_closeout(root)
    rows = closeout.get("rows") if isinstance(closeout, dict) else None
    feedback_rows: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        source_hypothesis_id = str(row.get("source_hypothesis_id") or "")
        feedback_rows.append(
            {
                "feedback_id": _content_id(
                    "qhf",
                    {
                        "source_hypothesis_id": source_hypothesis_id,
                        "final_generation_outcome": row.get("final_generation_outcome"),
                    },
                ),
                "source_hypothesis_id": source_hypothesis_id,
                "final_generation_outcome": str(row.get("final_generation_outcome") or ""),
                "campaign_readiness_state": str(row.get("campaign_readiness_state") or ""),
                "feedback_class": (
                    "positive_registration_feedback"
                    if str(row.get("final_generation_outcome") or "") == "RESEARCH_REGISTERED_AUTOMATED"
                    else "blocked_generation_feedback"
                ),
                "next_action": (
                    "preserve_campaign_blockers"
                    if str(row.get("campaign_readiness_state") or "") == "BLOCKED"
                    else "no_action"
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_generated_hypothesis_feedback",
        "generator_version": GENERATOR_VERSION,
        "rows": sorted(feedback_rows, key=lambda row: row["feedback_id"]),
        "summary": {
            "feedback_count": len(feedback_rows),
            "registered_feedback_count": sum(
                1 for row in feedback_rows if row["feedback_class"] == "positive_registration_feedback"
            ),
        },
        "provenance": ["generated_research/reports/automated_generation_closeout.v1.json"],
    }


def _closeout_outcome(compiled: dict[str, Any], submission: dict[str, Any]) -> str:
    admitted = compiled["summary"]["admitted_count"]
    submitted = submission["summary"]["submitted_count"]
    if admitted and submitted:
        return "HYPOTHESES_ADMITTED_AND_SUBMITTED"
    if admitted:
        return "HYPOTHESES_ADMITTED_GENERATION_BLOCKED"
    if compiled["summary"]["candidate_count"]:
        return "PARTIAL_AUTONOMOUS_HYPOTHESIS_CAPABILITY"
    return "NO_ADMISSIBLE_HYPOTHESES"


def _closeout_markdown(closeout: dict[str, Any]) -> str:
    summary = closeout["summary"]
    lines = [
        "# ADE-QRE-020 Automated Hypothesis Generation Closeout",
        "",
        f"- outcome: `{closeout['program_outcome']}`",
        f"- evidence snapshot: `{closeout['evidence_snapshot_id']}`",
        f"- opportunity count: `{summary['opportunity_count']}`",
        f"- candidate count: `{summary['candidate_count']}`",
        f"- admitted count: `{summary['admitted_count']}`",
        f"- submitted-to-ADE-QRE-019 count: `{summary['submitted_count']}`",
        f"- primitive-extension requests: `{summary['primitive_extension_request_count']}`",
        f"- next action: `{closeout['next_action']}`",
        "",
        "| thesis_id | source_hypothesis_id | lifecycle_state | compatibility | next_action |",
        "|---|---|---|---|---|",
    ]
    for row in closeout["candidate_rows"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["thesis_id"]),
                    str(row["source_hypothesis_id"]),
                    str(row["lifecycle_state"]),
                    str(row["primitive_compatibility"]),
                    str(row["next_action"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def run_automated_hypothesis_generation(
    *,
    repo_root: Path | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    snapshot = build_evidence_snapshot(repo_root=root)
    opportunities = detect_opportunities(repo_root=root)
    observations = build_observations(repo_root=root)
    mechanisms = build_mechanism_proposals(repo_root=root)
    compiled = compile_candidate_theses(repo_root=root)
    generated_registry = build_generated_thesis_registry(repo_root=root)
    resolved_catalog = build_resolved_thesis_catalog(repo_root=root)
    priorities = build_prioritization(repo_root=root)
    submission = integrate_with_ade_qre_019(repo_root=root)
    feedback = build_feedback(repo_root=root)
    closeout = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generator_version": GENERATOR_VERSION,
        "evidence_snapshot_id": snapshot["evidence_snapshot_id"],
        "program_outcome": _closeout_outcome(compiled, submission),
        "summary": {
            "opportunity_count": opportunities["summary"]["opportunity_count"],
            "observation_count": observations["summary"]["observation_count"],
            "mechanism_count": mechanisms["summary"]["mechanism_count"],
            "candidate_count": compiled["summary"]["candidate_count"],
            "admitted_count": compiled["summary"]["admitted_count"],
            "persisted_hypothesis_count": len(generated_registry["rows"]),
            "exact_duplicate_suppressed_count": compiled["summary"]["exact_duplicate_suppressed_count"],
            "near_duplicate_suppressed_count": compiled["summary"]["near_duplicate_suppressed_count"],
            "submitted_count": submission["summary"]["submitted_count"],
            "primitive_extension_request_count": compiled["summary"]["primitive_extension_request_count"],
            "generated_thesis_count": len(generated_registry["rows"]),
            "resolved_generated_count": resolved_catalog["summary"]["generated_count"],
            "candidate_limit": MAX_CANDIDATES_PER_INVOCATION,
            "persisted_hypothesis_limit": MAX_PERSISTED_HYPOTHESES_PER_INVOCATION,
        },
        "candidate_rows": compiled["rows"],
        "admitted_rows": compiled["admitted_rows"],
        "primitive_extension_requests": compiled["primitive_extension_requests"],
        "submission_rows": submission["rows"],
        "feedback_rows": feedback["rows"],
        "next_action": (
            "extend_primitives_or_resolve_identity_before_resubmission"
            if compiled["summary"]["admitted_count"]
            else "preserve_fail_closed_hypothesis_pipeline_and_authoritative_blockers"
        ),
        "provenance": sorted(
            set(
                snapshot["provenance"]
                + opportunities["provenance"]
                + feedback["provenance"]
            )
        ),
    }
    artifacts = {
        EVIDENCE_SNAPSHOT_PATH: snapshot,
        OPPORTUNITIES_PATH: opportunities,
        OBSERVATIONS_PATH: observations,
        MECHANISMS_PATH: mechanisms,
        CANDIDATES_PATH: {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "qre_generated_candidate_theses_rows",
            "rows": compiled["rows"],
            "summary": compiled["summary"],
        },
        GENERATED_THESIS_REGISTRY_PATH: generated_registry,
        RESOLVED_THESIS_CATALOG_PATH: resolved_catalog,
        REJECTIONS_PATH: {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "qre_generated_thesis_rejections",
            "rows": compiled["rejection_rows"],
            "summary": {"rejection_count": len(compiled["rejection_rows"])},
        },
        PRIORITIES_PATH: priorities,
        PRIMITIVE_EXTENSION_REQUESTS_PATH: {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "qre_primitive_extension_requests",
            "rows": compiled["primitive_extension_requests"],
            "summary": {
                "primitive_extension_request_count": len(compiled["primitive_extension_requests"])
            },
        },
        FEEDBACK_PATH: feedback,
        INTEGRATED_CLOSEOUT_PATH: closeout,
    }
    if write_outputs:
        for path, payload in artifacts.items():
            _atomic_write(root / path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        _atomic_write(root / INTEGRATED_CLOSEOUT_MD_PATH, _closeout_markdown(closeout))
    return closeout


__all__ = [
    "COMPATIBILITY_STATES",
    "GENERATOR_VERSION",
    "MECHANISM_CLASSES",
    "NOVELTY_OUTCOMES",
    "OPPORTUNITY_CLASSES",
    "PROGRAM_OUTCOMES",
    "SCHEMA_VERSION",
    "SCIENTIFIC_REASONS",
    "TESTABILITY_STATES",
    "THESIS_LIFECYCLE_STATES",
    "build_evidence_snapshot",
    "build_generated_thesis_registry",
    "build_mechanism_proposals",
    "build_observations",
    "build_prioritization",
    "build_resolved_thesis_catalog",
    "compile_candidate_theses",
    "detect_opportunities",
    "integrate_with_ade_qre_019",
    "run_automated_hypothesis_generation",
    "stable_digest",
]


def main() -> None:
    run_automated_hypothesis_generation(repo_root=REPO_ROOT)


if __name__ == "__main__":
    main()
