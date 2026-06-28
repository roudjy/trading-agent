from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_campaign_portfolio_plan"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017w-2026-06-28"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_campaign_portfolio_plan")
LATEST_NAME: Final[str] = "latest.json"
LATEST_MARKDOWN_NAME: Final[str] = "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_campaign_portfolio_plan.md")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_OPERATOR_REPORT_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
DEFAULT_WHY_SURFACES_PATH: Final[Path] = Path("logs/qre_why_surfaces/latest.json")
DEFAULT_SUPPRESSION_PATH: Final[Path] = Path("logs/qre_suppression_efficacy/latest.json")
DEFAULT_DEDUP_PATH: Final[Path] = Path("logs/qre_experiment_dedup_novelty_enforcement/latest.json")
DEFAULT_ROUTER_PATH: Final[Path] = Path("logs/qre_research_cycle_router/latest.json")
DEFAULT_PRIOR_FAILURE_PATH: Final[Path] = Path("logs/qre_prior_failure_retrieval/latest.json")
DEFAULT_SOURCE_USEFULNESS_PATH: Final[Path] = Path("logs/qre_source_usefulness_ledger/latest.json")
DEFAULT_SOURCE_IDENTITY_PATH: Final[Path] = Path(
    "logs/qre_source_identity_authority_normalization/latest.json"
)
DEFAULT_CACHE_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
DEFAULT_BREADTH_PATH: Final[Path] = Path("logs/qre_evidence_breadth_framework/latest.json")
DEFAULT_HYPOTHESIS_CATALOG_PATH: Final[Path] = Path(
    "research/strategy_hypothesis_catalog_latest.v1.json"
)
DEFAULT_CAMPAIGN_METADATA_PATH: Final[Path] = Path(
    "research/strategy_campaign_metadata_latest.v1.json"
)
DEFAULT_TEMPLATES_PATH: Final[Path] = Path("research/campaign_templates_latest.v1.json")
DEFAULT_PRESET_POLICY_PATH: Final[Path] = Path("research/preset_policy_state_latest.v1.json")
DEFAULT_CAMPAIGN_REGISTRY_PATH: Final[Path] = Path("research/campaign_registry_latest.v1.json")
DEFAULT_SAMPLING_PLAN_PATH: Final[Path] = Path(
    "research/campaign_preregistered_sampling_plan_latest.v1.json"
)
DEFAULT_MULTIWINDOW_RUN_PATH: Final[Path] = Path(
    "logs/qre_preregistered_multiwindow_evidence_run/latest.json"
)
DEFAULT_BUDGET_PATH: Final[Path] = Path("research/campaign_budget_latest.v1.json")
DEFAULT_PRESETS_SOURCE_PATH: Final[Path] = Path("research/presets.py")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_campaign_portfolio_plan/",
    "docs/governance/qre_campaign_portfolio_plan.md",
)
VALID_INCLUSION_STATUSES: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "READY_WITH_LIMITATIONS",
    "BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "EXCLUDED_DUPLICATE",
    "EXCLUDED_DEAD_ZONE",
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


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _normalize_sequence(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _text(item))]
    text = _text(value)
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return out


def _index_by(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _text(row.get(field))
        if key:
            indexed[key] = dict(row)
    return indexed


def _stable_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _read_presets_source(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return None


def _literal(node: ast.AST, constants: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_literal(item, constants) for item in node.elts)
    if isinstance(node, ast.List):
        return [_literal(item, constants) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _literal(key, constants): _literal(value, constants)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def parse_preset_catalog(presets_source: str | None) -> list[dict[str, Any]]:
    if not presets_source:
        return []
    tree = ast.parse(presets_source)
    constants: dict[str, Any] = {}
    catalog: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "PRESETS" and isinstance(node.value, ast.Tuple):
                for item in node.value.elts:
                    if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name):
                        continue
                    if item.func.id != "ResearchPreset":
                        continue
                    row: dict[str, Any] = {}
                    for keyword in item.keywords:
                        if keyword.arg is None:
                            continue
                        row[keyword.arg] = _literal(keyword.value, constants)
                    catalog.append(row)
                continue
            value = _literal(node.value, constants) if node.value is not None else None
            if value is not None:
                constants[node.target.id] = value
            continue
        if isinstance(node, ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "PRESETS"
                and isinstance(node.value, ast.Tuple)
            ):
                for item in node.value.elts:
                    if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name):
                        continue
                    if item.func.id != "ResearchPreset":
                        continue
                    row: dict[str, Any] = {}
                    for keyword in item.keywords:
                        if keyword.arg is None:
                            continue
                        row[keyword.arg] = _literal(keyword.value, constants)
                    catalog.append(row)
                continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value = _literal(node.value, constants)
            if value is not None:
                constants[name] = value
            continue
    return [row for row in catalog if _text(row.get("name"))]


def _coverage_range(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mins = [row.get("min_timestamp_utc") for row in rows if _text(row.get("min_timestamp_utc"))]
    maxes = [row.get("max_timestamp_utc") for row in rows if _text(row.get("max_timestamp_utc"))]
    return {
        "min_timestamp_utc": min(mins) if mins else "",
        "max_timestamp_utc": max(maxes) if maxes else "",
    }


def _data_readiness(
    preset_row: dict[str, Any] | None,
    *,
    coverage_by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    if not preset_row:
        return {
            "status": "not_scoped_to_preset",
            "ready_asset_count": 0,
            "total_asset_count": 0,
            "coverage_ratio": 0.0,
            "assets": [],
        }
    assets = [asset for asset in preset_row.get("universe") or () if _text(asset)]
    timeframe = _text(preset_row.get("timeframe"))
    coverage_rows = [coverage_by_key.get((asset, timeframe)) for asset in assets]
    ready_count = sum(1 for row in coverage_rows if isinstance(row, dict) and bool(row.get("ready")))
    total_count = len(assets)
    status = "ready" if total_count and ready_count == total_count else "partial" if ready_count else "missing"
    visible_rows = [row for row in coverage_rows if isinstance(row, dict)]
    coverage_range = _coverage_range(visible_rows)
    return {
        "status": status,
        "ready_asset_count": ready_count,
        "total_asset_count": total_count,
        "coverage_ratio": round(ready_count / total_count, 6) if total_count else 0.0,
        "coverage_range": coverage_range,
        "assets": [
            {
                "asset": asset,
                "present": isinstance(row, dict),
                "ready": bool(row.get("ready")) if isinstance(row, dict) else False,
                "row_count": row.get("row_count") if isinstance(row, dict) else None,
                "min_timestamp_utc": row.get("min_timestamp_utc") if isinstance(row, dict) else "",
                "max_timestamp_utc": row.get("max_timestamp_utc") if isinstance(row, dict) else "",
            }
            for asset, row in zip(assets, coverage_rows)
        ],
    }


def _identity_readiness(
    preset_row: dict[str, Any] | None,
    *,
    identity_by_symbol: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not preset_row:
        return {
            "status": "not_scoped_to_preset",
            "ready_asset_count": 0,
            "total_asset_count": 0,
            "coverage_ratio": 0.0,
            "assets": [],
        }
    assets = [asset for asset in preset_row.get("universe") or () if _text(asset)]
    rows = [identity_by_symbol.get(asset) for asset in assets]
    ready_count = sum(
        1
        for row in rows
        if isinstance(row, dict) and _text(row.get("authority_status")) == "normalized_context_ready"
    )
    total_count = len(assets)
    status = "ready" if total_count and ready_count == total_count else "partial" if ready_count else "missing"
    return {
        "status": status,
        "ready_asset_count": ready_count,
        "total_asset_count": total_count,
        "coverage_ratio": round(ready_count / total_count, 6) if total_count else 0.0,
        "assets": [
            {
                "asset": asset,
                "present": isinstance(row, dict),
                "authority_status": _text((row or {}).get("authority_status")),
                "instrument_identity_status": _text((row or {}).get("instrument_identity_status")),
                "source_identity_status": _text((row or {}).get("source_identity_status")),
            }
            for asset, row in zip(assets, rows)
        ],
    }


def _window_state(
    *,
    label: str,
    preset_row: dict[str, Any] | None,
    data_readiness: dict[str, Any],
    sampling_plan: dict[str, Any],
    multiwindow_run: dict[str, Any],
) -> dict[str, Any]:
    coverage_range = dict(data_readiness.get("coverage_range") or {})
    sampling_scope = sampling_plan.get("sampling_plan") if isinstance(sampling_plan.get("sampling_plan"), dict) else {}
    if label == "train":
        if not preset_row:
            return {"status": "not_scoped_to_preset"}
        return {
            "status": "range_visible_unassigned" if coverage_range.get("min_timestamp_utc") else "missing",
            "min_timestamp_utc": coverage_range.get("min_timestamp_utc", ""),
            "max_timestamp_utc": coverage_range.get("max_timestamp_utc", ""),
        }
    if label == "validation":
        window_defs = sampling_scope.get("window_definitions")
        if isinstance(window_defs, list) and window_defs:
            return {
                "status": "window_materialized",
                "window_count": len(window_defs),
                "window_definitions": list(window_defs),
            }
        if sampling_scope:
            return {
                "status": _text(sampling_scope.get("status")) or "coverage_required_not_materialized",
                "window_count": len(window_defs) if isinstance(window_defs, list) else 0,
                "minimum_window_length": sampling_scope.get("minimum_window_length"),
                "minimum_common_trading_dates": (
                    ((sampling_plan.get("coverage_requirements") or {}).get("minimum_common_trading_dates"))
                    if isinstance(sampling_plan.get("coverage_requirements"), dict)
                    else None
                ),
            }
        return {"status": "not_materialized"}
    if multiwindow_run:
        accepted_count = multiwindow_run.get("accepted_oos_count")
        failed_count = multiwindow_run.get("failed_window_count")
        if isinstance(accepted_count, int) or isinstance(failed_count, int):
            return {
                "status": "no_accepted_oos" if int(accepted_count or 0) == 0 else "accepted_oos_visible",
                "accepted_oos_count": accepted_count,
                "accepted_window_count": multiwindow_run.get("accepted_window_count"),
                "failed_window_count": failed_count,
                "positive_oos_trade_count_total": multiwindow_run.get("positive_oos_trade_count_total"),
            }
    return {"status": "not_materialized"}


def _null_control_feasibility(
    registry_row: dict[str, Any],
    *,
    sampling_plan: dict[str, Any],
    multiwindow_run: dict[str, Any],
) -> dict[str, Any]:
    registry_controls = _normalize_sequence(registry_row.get("null_controls"))
    run_controls = (
        multiwindow_run.get("null_control_results")
        if isinstance(multiwindow_run.get("null_control_results"), dict)
        else {}
    )
    sampling_scope = sampling_plan.get("sampling_plan") if isinstance(sampling_plan.get("sampling_plan"), dict) else {}
    defined_controls = sampling_scope.get("null_control_definitions")
    if isinstance(run_controls, dict) and _text(run_controls.get("status")):
        return {
            "status": _text(run_controls.get("status")),
            "registry_controls": registry_controls,
            "defined_controls": list(defined_controls) if isinstance(defined_controls, list) else [],
            "missing_control_ids": _normalize_sequence(run_controls.get("missing_control_ids")),
            "recommended_next_action": _text(run_controls.get("recommended_next_action")),
        }
    if isinstance(defined_controls, list) and defined_controls:
        return {
            "status": "defined_not_materialized",
            "registry_controls": registry_controls,
            "defined_controls": list(defined_controls),
            "missing_control_ids": [],
            "recommended_next_action": "",
        }
    return {
        "status": "not_materialized" if registry_controls else "not_visible",
        "registry_controls": registry_controls,
        "defined_controls": [],
        "missing_control_ids": [],
        "recommended_next_action": "",
    }


def _cost_and_slippage_readiness(
    preset_row: dict[str, Any] | None,
    hypothesis_row: dict[str, Any],
) -> dict[str, Any]:
    cost_class = _text(hypothesis_row.get("cost_class"))
    cost_mode = _text((preset_row or {}).get("cost_mode"))
    if cost_mode and cost_class:
        return {
            "status": "cost_mode_visible_slippage_not_materialized",
            "cost_mode": cost_mode,
            "cost_class": cost_class,
            "slippage_visible": False,
        }
    if cost_class:
        return {
            "status": "cost_class_visible_only",
            "cost_mode": cost_mode,
            "cost_class": cost_class,
            "slippage_visible": False,
        }
    return {"status": "missing", "cost_mode": cost_mode, "cost_class": cost_class, "slippage_visible": False}


def _compute_estimate(
    preset_name: str,
    *,
    templates_by_preset: dict[str, list[dict[str, Any]]],
    budget_report: dict[str, Any],
) -> dict[str, Any]:
    template_rows = templates_by_preset.get(preset_name, [])
    runtimes = [
        int(row.get("estimated_runtime_seconds_default") or 0)
        for row in template_rows
        if isinstance(row.get("estimated_runtime_seconds_default"), int)
    ]
    if not runtimes:
        return {
            "status": "missing",
            "estimated_runtime_seconds_default": None,
            "template_ids": [],
            "daily_compute_budget_seconds": budget_report.get("daily_compute_budget_seconds"),
            "lease_ttl_seconds": None,
        }
    config = budget_report if isinstance(budget_report, dict) else {}
    return {
        "status": "template_estimate_visible",
        "estimated_runtime_seconds_default": min(runtimes),
        "template_ids": sorted(_text(row.get("template_id")) for row in template_rows if _text(row.get("template_id"))),
        "daily_compute_budget_seconds": config.get("daily_compute_budget_seconds"),
        "lease_ttl_seconds": config.get("lease_ttl_seconds"),
    }


def _timeout_risk(compute_estimate: dict[str, Any]) -> dict[str, Any]:
    runtime = compute_estimate.get("estimated_runtime_seconds_default")
    lease_ttl = compute_estimate.get("lease_ttl_seconds")
    budget = compute_estimate.get("daily_compute_budget_seconds")
    if isinstance(runtime, int) and isinstance(lease_ttl, int) and isinstance(budget, int):
        return {
            "status": "bounded_by_visible_runtime_and_lease" if runtime <= lease_ttl <= budget else "runtime_budget_tension_visible",
            "estimated_runtime_seconds_default": runtime,
            "lease_ttl_seconds": lease_ttl,
            "daily_compute_budget_seconds": budget,
        }
    return {"status": "insufficient_evidence"}


def _signal_density(registry_row: dict[str, Any]) -> dict[str, Any]:
    value = _text(registry_row.get("signal_density_expectation"))
    if not value:
        return {"status": "missing", "value": ""}
    if value == "blocked":
        return {"status": "unsupported", "value": value}
    return {"status": "visible", "value": value}


def _minimum_sample(registry_row: dict[str, Any]) -> dict[str, Any]:
    value = _text(registry_row.get("minimum_sample"))
    if not value:
        return {"status": "missing", "value": ""}
    if value.startswith("blocked:") or value == "campaign_specific_minimum_sample_required_before_support":
        return {"status": "needs_materialization", "value": value}
    return {"status": "visible", "value": value}


def _expected_trade_count(
    *,
    multiwindow_run: dict[str, Any],
) -> dict[str, Any]:
    value = multiwindow_run.get("positive_oos_trade_count_total")
    if isinstance(value, int):
        return {
            "status": "observed_from_existing_oos_run",
            "value": value,
        }
    return {"status": "insufficient_evidence", "value": None}


def _source_readiness(source_usefulness_report: dict[str, Any]) -> dict[str, Any]:
    summary = source_usefulness_report.get("summary") if isinstance(source_usefulness_report, dict) else {}
    rows = _read_rows(source_usefulness_report, "rows")
    source_ids = _dedupe(_normalize_sequence([row.get("source_id") for row in rows]))
    return {
        "status": "ready" if bool((summary or {}).get("research_ready")) else "missing",
        "ready_source_count": (summary or {}).get("ready_source_count"),
        "source_count": (summary or {}).get("source_count"),
        "cache_manifest_ready": (summary or {}).get("cache_manifest_ready"),
        "source_ids": source_ids,
    }


def _find_breadth_recommendation(
    registry_row: dict[str, Any],
    *,
    preset_name: str,
    breadth_recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
    behavior_family = _text(registry_row.get("behavior_family"))
    candidates = [
        row
        for row in breadth_recommendations
        if preset_name
        and preset_name
        and preset_name in (_text(row.get("scope_key")) + _text(row.get("scope_label")))
    ]
    if candidates:
        return dict(candidates[0])
    candidates = [
        row
        for row in breadth_recommendations
        if source_hypothesis_id in (_text(row.get("scope_key")) + _text(row.get("scope_label")))
        or behavior_family in (_text(row.get("scope_key")) + _text(row.get("scope_label")))
    ]
    return dict(candidates[0]) if candidates else {}


def _expected_information_gain(
    *,
    inclusion_status: str,
    breadth_row: dict[str, Any],
    operator_row: dict[str, Any],
) -> dict[str, Any]:
    if inclusion_status in {"EXCLUDED_DEAD_ZONE", "EXCLUDED_DUPLICATE"}:
        return {
            "status": "suppressed_repeat_scope",
            "priority_score": breadth_row.get("priority_score"),
            "rationale": "Current evidence treats this scope as a low-value repeat rather than new information gain.",
        }
    if _text(operator_row.get("final_decision")) == "REJECTED":
        return {
            "status": "negative_existing_scope_evidence",
            "priority_score": breadth_row.get("priority_score"),
            "rationale": "Thesis-level operator evidence is already negative and does not justify a new ready cell.",
        }
    if breadth_row:
        return {
            "status": "breadth_gap_visible",
            "priority_score": breadth_row.get("priority_score"),
            "rationale": _text(breadth_row.get("reason")),
        }
    return {"status": "insufficient_evidence", "priority_score": None, "rationale": "No scoped breadth signal is materialized."}


def _duplicate_and_dead_zone_state(
    registry_row: dict[str, Any],
    *,
    preset_name: str,
    prior_failure_row: dict[str, Any],
    dedup_rows: list[dict[str, Any]],
    campaigns_by_key: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
    dead_zone_count = int(prior_failure_row.get("dead_zone_count") or 0)
    dead_zone_items = [
        item
        for item in prior_failure_row.get("retrieval_items") or []
        if isinstance(item, dict) and _text(item.get("retrieval_kind")) == "dead_zone"
    ]
    duplicate_rows = [row for row in dedup_rows if _text(row.get("duplicate_class")) != "duplicate_low_value_run_pressure"]
    exact_campaign = campaigns_by_key.get((source_hypothesis_id, preset_name))
    is_exact_failed_scope = bool(
        preset_name
        and exact_campaign
        and dead_zone_items
        and any(_text(row.get("duplicate_class")) == "exact_failed_scope" for row in duplicate_rows)
    )
    duplicate_state = {
        "status": "suppressed_exact_failed_scope_visible" if is_exact_failed_scope else "no_cell_specific_duplicate_evidence",
        "duplicate_classes": sorted(
            _text(row.get("duplicate_class")) for row in duplicate_rows if _text(row.get("duplicate_class"))
        ),
        "exact_next_action": _text(next((row.get("exact_next_action") for row in duplicate_rows if _text(row.get("exact_next_action"))), "")),
    }
    dead_zone_state = {
        "status": "dead_zone_visible" if dead_zone_count > 0 else "not_visible",
        "dead_zone_count": dead_zone_count,
        "retrieval_refs": _dedupe(
            _normalize_sequence(
                [
                    item.get("retrieval_ref")
                    for item in dead_zone_items
                    if isinstance(item, dict) and _text(item.get("retrieval_ref"))
                ]
            )
        ),
    }
    return duplicate_state, dead_zone_state


def _candidate_status(
    registry_row: dict[str, Any],
    *,
    preset_row: dict[str, Any] | None,
    operator_row: dict[str, Any],
    hypothesis_row: dict[str, Any],
    data_readiness: dict[str, Any],
    identity_readiness: dict[str, Any],
    null_controls: dict[str, Any],
    oos_window: dict[str, Any],
    duplicate_state: dict[str, Any],
    dead_zone_state: dict[str, Any],
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
    hypothesis_status = _text(hypothesis_row.get("status"))
    if _text(duplicate_state.get("status")) == "suppressed_exact_failed_scope_visible" and _text(
        dead_zone_state.get("status")
    ) == "dead_zone_visible":
        return "EXCLUDED_DEAD_ZONE", [
            "exact_failed_scope_suppressed",
            "dead_zone_retrieval_visible",
        ]
    if not preset_row:
        if hypothesis_status in {"disabled", "diagnostic"} or _text(registry_row.get("status")) == "blocked":
            blockers.extend(
                [
                    "no_executable_preset_mapping",
                    "eligible_campaign_types_empty",
                    "thesis_status_not_executable",
                ]
            )
            return "BLOCKED", blockers
        blockers.extend(
            [
                "no_executable_preset_mapping",
                "eligible_campaign_types_empty",
                "campaign_scope_not_materialized",
            ]
        )
        return "INSUFFICIENT_EVIDENCE", blockers
    if _text(operator_row.get("final_decision")) == "REJECTED":
        blockers.extend(
            [
                "operator_report_rejected_thesis",
                "accepted_oos_count_zero",
                "null_controls_incomplete",
            ]
        )
        return "BLOCKED", blockers
    if _text(operator_row.get("final_decision")) == "BLOCKED":
        blockers.extend(_normalize_sequence((operator_row.get("lineage_completeness") or {}).get("missing_lineage_fields")))
    if _text(data_readiness.get("status")) != "ready":
        blockers.append("data_readiness_incomplete")
    if _text(identity_readiness.get("status")) != "ready":
        blockers.append("identity_readiness_incomplete")
    if _text(oos_window.get("status")) in {"not_materialized", "no_accepted_oos", ""}:
        blockers.append("oos_unavailable_or_unproven")
    if _text(null_controls.get("status")) not in {"ready", "completed", "passed"}:
        blockers.append("null_controls_incomplete")
    if blockers:
        return "BLOCKED", _dedupe(blockers)
    return "READY_FOR_PREREGISTRATION", []


def _cell_id(thesis_id: str, preset_name: str, timeframe: str, assets: list[str]) -> str:
    digest = _stable_digest(
        {
            "thesis_id": thesis_id,
            "preset_name": preset_name,
            "timeframe": timeframe,
            "assets": assets,
        }
    )
    return f"qcp_{digest[:16]}"


def _portfolio_identity(rows: list[dict[str, Any]]) -> str:
    digest = _stable_digest(
        [
            {
                "cell_id": _text(row.get("cell_id")),
                "inclusion_status": _text(row.get("inclusion_status")),
                "next_action": _text(row.get("next_action")),
            }
            for row in rows
        ]
    )
    return f"qcpp_{digest[:16]}"


def build_campaign_portfolio_plan(
    *,
    repo_root: Path | None = None,
    registry_report: dict[str, Any] | None = None,
    operator_report: dict[str, Any] | None = None,
    why_report: dict[str, Any] | None = None,
    suppression_report: dict[str, Any] | None = None,
    dedup_report: dict[str, Any] | None = None,
    router_report: dict[str, Any] | None = None,
    prior_failure_report: dict[str, Any] | None = None,
    source_usefulness_report: dict[str, Any] | None = None,
    source_identity_report: dict[str, Any] | None = None,
    cache_report: dict[str, Any] | None = None,
    breadth_report: dict[str, Any] | None = None,
    hypothesis_catalog_report: dict[str, Any] | None = None,
    campaign_metadata_report: dict[str, Any] | None = None,
    templates_report: dict[str, Any] | None = None,
    preset_policy_report: dict[str, Any] | None = None,
    campaign_registry_report: dict[str, Any] | None = None,
    sampling_plan_report: dict[str, Any] | None = None,
    multiwindow_run_report: dict[str, Any] | None = None,
    budget_report: dict[str, Any] | None = None,
    preset_catalog: list[dict[str, Any]] | None = None,
    presets_source: str | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry_report = registry_report or _read_json(root / DEFAULT_REGISTRY_PATH) or {}
    operator_report = operator_report or _read_json(root / DEFAULT_OPERATOR_REPORT_PATH) or {}
    why_report = why_report or _read_json(root / DEFAULT_WHY_SURFACES_PATH) or {}
    suppression_report = suppression_report or _read_json(root / DEFAULT_SUPPRESSION_PATH) or {}
    dedup_report = dedup_report or _read_json(root / DEFAULT_DEDUP_PATH) or {}
    router_report = router_report or _read_json(root / DEFAULT_ROUTER_PATH) or {}
    prior_failure_report = prior_failure_report or _read_json(root / DEFAULT_PRIOR_FAILURE_PATH) or {}
    source_usefulness_report = source_usefulness_report or _read_json(root / DEFAULT_SOURCE_USEFULNESS_PATH) or {}
    source_identity_report = source_identity_report or _read_json(root / DEFAULT_SOURCE_IDENTITY_PATH) or {}
    cache_report = cache_report or _read_json(root / DEFAULT_CACHE_PATH) or {}
    breadth_report = breadth_report or _read_json(root / DEFAULT_BREADTH_PATH) or {}
    hypothesis_catalog_report = hypothesis_catalog_report or _read_json(root / DEFAULT_HYPOTHESIS_CATALOG_PATH) or {}
    campaign_metadata_report = campaign_metadata_report or _read_json(root / DEFAULT_CAMPAIGN_METADATA_PATH) or {}
    templates_report = templates_report or _read_json(root / DEFAULT_TEMPLATES_PATH) or {}
    preset_policy_report = preset_policy_report or _read_json(root / DEFAULT_PRESET_POLICY_PATH) or {}
    campaign_registry_report = campaign_registry_report or _read_json(root / DEFAULT_CAMPAIGN_REGISTRY_PATH) or {}
    sampling_plan_report = sampling_plan_report or _read_json(root / DEFAULT_SAMPLING_PLAN_PATH) or {}
    multiwindow_run_report = multiwindow_run_report or _read_json(root / DEFAULT_MULTIWINDOW_RUN_PATH) or {}
    budget_report = budget_report or _read_json(root / DEFAULT_BUDGET_PATH) or {}
    presets_source = presets_source if presets_source is not None else _read_presets_source(root / DEFAULT_PRESETS_SOURCE_PATH)
    preset_catalog = preset_catalog if preset_catalog is not None else parse_preset_catalog(presets_source)

    registry_rows = _read_rows(registry_report, "rows")
    operator_by_source = _index_by(_read_rows(operator_report, "rows"), "source_hypothesis_id")
    why_by_source = _index_by(_read_rows(why_report, "rows"), "source_hypothesis_id")
    prior_by_source = _index_by(_read_rows(prior_failure_report, "rows"), "source_hypothesis_id")
    hypothesis_by_id = {
        _text(row.get("hypothesis_id")): dict(row)
        for row in hypothesis_catalog_report.get("hypotheses", [])
        if isinstance(row, dict) and _text(row.get("hypothesis_id"))
    }
    campaign_meta_by_id = {
        key: dict(value)
        for key, value in (campaign_metadata_report.get("hypotheses") or {}).items()
        if isinstance(value, dict) and _text(key)
    }
    templates_by_preset: dict[str, list[dict[str, Any]]] = {}
    for row in templates_report.get("templates") or []:
        if not isinstance(row, dict):
            continue
        preset_name = _text(row.get("preset_name"))
        if preset_name:
            templates_by_preset.setdefault(preset_name, []).append(dict(row))
    preset_policy_by_name = {
        key: dict(value)
        for key, value in (preset_policy_report.get("presets") or {}).items()
        if isinstance(value, dict) and _text(key)
    }
    preset_rows = [dict(row) for row in preset_catalog if isinstance(row, dict)]
    presets_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for row in preset_rows:
        hypothesis_id = _text(row.get("hypothesis_id"))
        if hypothesis_id:
            presets_by_hypothesis.setdefault(hypothesis_id, []).append(row)
    coverage_rows = cache_report.get("coverage") or []
    coverage_by_key = {
        (_text(row.get("instrument")), _text(row.get("timeframe"))): dict(row)
        for row in coverage_rows
        if isinstance(row, dict) and _text(row.get("instrument")) and _text(row.get("timeframe"))
    }
    identity_by_symbol = _index_by(_read_rows(source_identity_report, "rows"), "symbol")
    campaigns_by_key = {
        (_text(row.get("hypothesis_id")), _text(row.get("preset_name"))): dict(row)
        for row in (campaign_registry_report.get("campaigns") or {}).values()
        if isinstance(row, dict)
    }
    breadth_recommendations = [
        dict(row)
        for row in breadth_report.get("breadth_priority_recommendations") or []
        if isinstance(row, dict)
    ]
    dedup_rows = [
        dict(row)
        for row in dedup_report.get("duplicate_rows") or []
        if isinstance(row, dict)
    ]

    rows: list[dict[str, Any]] = []
    for registry_row in sorted(registry_rows, key=lambda row: (_text(row.get("source_hypothesis_id")), _text(row.get("thesis_id")))):
        source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
        thesis_id = _text(registry_row.get("thesis_id"))
        operator_row = operator_by_source.get(source_hypothesis_id, {})
        why_row = why_by_source.get(source_hypothesis_id, {})
        prior_failure_row = prior_by_source.get(source_hypothesis_id, {})
        hypothesis_row = hypothesis_by_id.get(source_hypothesis_id, {})
        campaign_meta_row = campaign_meta_by_id.get(source_hypothesis_id, {})
        scoped_presets = sorted(
            presets_by_hypothesis.get(source_hypothesis_id, []),
            key=lambda row: (_text(row.get("name")), _text(row.get("timeframe"))),
        )
        if not scoped_presets:
            scoped_presets = [{}]
        for preset_row in scoped_presets:
            preset_name = _text(preset_row.get("name"))
            matched_campaign = campaigns_by_key.get((source_hypothesis_id, preset_name), {})
            matched_sampling_plan = (
                sampling_plan_report
                if _text((sampling_plan_report.get("campaign_scope") or {}).get("hypothesis_id")) == source_hypothesis_id
                and _text((sampling_plan_report.get("campaign_scope") or {}).get("preset_name")) == preset_name
                else {}
            )
            matched_multiwindow_run = (
                multiwindow_run_report
                if _text((multiwindow_run_report.get("campaign_scope") or {}).get("hypothesis_id")) == source_hypothesis_id
                and _text((multiwindow_run_report.get("campaign_scope") or {}).get("preset_name")) == preset_name
                else {}
            )
            data_readiness = _data_readiness(preset_row or None, coverage_by_key=coverage_by_key)
            identity_readiness = _identity_readiness(preset_row or None, identity_by_symbol=identity_by_symbol)
            duplicate_state, dead_zone_state = _duplicate_and_dead_zone_state(
                registry_row,
                preset_name=preset_name,
                prior_failure_row=prior_failure_row,
                dedup_rows=dedup_rows,
                campaigns_by_key=campaigns_by_key,
            )
            null_controls = _null_control_feasibility(
                registry_row,
                sampling_plan=matched_sampling_plan,
                multiwindow_run=matched_multiwindow_run,
            )
            train_window = _window_state(
                label="train",
                preset_row=preset_row or None,
                data_readiness=data_readiness,
                sampling_plan=matched_sampling_plan,
                multiwindow_run=matched_multiwindow_run,
            )
            validation_window = _window_state(
                label="validation",
                preset_row=preset_row or None,
                data_readiness=data_readiness,
                sampling_plan=matched_sampling_plan,
                multiwindow_run=matched_multiwindow_run,
            )
            oos_window = _window_state(
                label="oos",
                preset_row=preset_row or None,
                data_readiness=data_readiness,
                sampling_plan=matched_sampling_plan,
                multiwindow_run=matched_multiwindow_run,
            )
            inclusion_status, blocker_reasons = _candidate_status(
                registry_row,
                preset_row=preset_row or None,
                operator_row=operator_row,
                hypothesis_row=hypothesis_row,
                data_readiness=data_readiness,
                identity_readiness=identity_readiness,
                null_controls=null_controls,
                oos_window=oos_window,
                duplicate_state=duplicate_state,
                dead_zone_state=dead_zone_state,
            )
            if inclusion_status not in VALID_INCLUSION_STATUSES:
                raise ValueError(f"invalid inclusion status: {inclusion_status}")
            breadth_row = _find_breadth_recommendation(
                registry_row,
                preset_name=preset_name,
                breadth_recommendations=breadth_recommendations,
            )
            next_action = (
                _text(duplicate_state.get("exact_next_action"))
                if inclusion_status in {"EXCLUDED_DEAD_ZONE", "EXCLUDED_DUPLICATE"}
                else _text(operator_row.get("next_action"))
                or _text(breadth_row.get("recommended_next_action"))
                or "collect_missing_evidence"
            )
            compute_estimate = _compute_estimate(
                preset_name,
                templates_by_preset=templates_by_preset,
                budget_report=(templates_report.get("config") or budget_report),
            )
            assets = [asset for asset in (preset_row.get("universe") or ()) if _text(asset)]
            cell = {
                "cell_id": _cell_id(
                    thesis_id,
                    preset_name,
                    _text(preset_row.get("timeframe")) or _text(registry_row.get("timeframe")),
                    assets,
                ),
                "thesis_id": thesis_id,
                "source_hypothesis_id": source_hypothesis_id,
                "title": _text(registry_row.get("title")),
                "preset_name": preset_name,
                "thesis_scope_kind": "preset_cell" if preset_name else "thesis_only_gap",
                "behavior_family": _text(registry_row.get("behavior_family")),
                "mechanism": _text(registry_row.get("mechanism")),
                "expected_behavior": _text(registry_row.get("expected_behavior")),
                "proposed_universe": (
                    list(assets)
                    if assets
                    else _text(registry_row.get("universe"))
                ),
                "proposed_assets_or_basket": list(assets),
                "proposed_timeframe": _text(preset_row.get("timeframe")) or _text(registry_row.get("timeframe")),
                "proposed_regime_coverage": _text(registry_row.get("regime_context")),
                "supporting_evidence": _normalize_sequence(registry_row.get("supporting_evidence")),
                "contradicting_evidence": _normalize_sequence(registry_row.get("contradicting_evidence")),
                "source_readiness": _source_readiness(source_usefulness_report),
                "data_readiness": data_readiness,
                "identity_readiness": identity_readiness,
                "expected_signal_density": _signal_density(registry_row),
                "minimum_sample": _minimum_sample(registry_row),
                "expected_trade_count": _expected_trade_count(multiwindow_run=matched_multiwindow_run),
                "minimum_required_window_length": (
                    ((matched_sampling_plan.get("coverage_requirements") or {}).get("minimum_window_length"))
                    if isinstance(matched_sampling_plan.get("coverage_requirements"), dict)
                    else None
                ),
                "available_train_window": train_window,
                "available_validation_window": validation_window,
                "available_oos_window": oos_window,
                "null_control_feasibility": null_controls,
                "cost_and_slippage_readiness": _cost_and_slippage_readiness(preset_row or None, hypothesis_row),
                "compute_estimate": compute_estimate,
                "timeout_risk": _timeout_risk(compute_estimate),
                "duplicate_risk_status": duplicate_state,
                "dead_zone_status": dead_zone_state,
                "expected_information_gain": _expected_information_gain(
                    inclusion_status=inclusion_status,
                    breadth_row=breadth_row,
                    operator_row=operator_row,
                ),
                "inclusion_status": inclusion_status,
                "blocker_reasons": blocker_reasons,
                "next_action": next_action,
                "operator_decision": _text(operator_row.get("final_decision")),
                "campaign_templates": sorted(
                    _text(row.get("template_id"))
                    for row in templates_by_preset.get(preset_name, [])
                    if _text(row.get("template_id"))
                ),
                "eligible_campaign_types": _normalize_sequence(
                    campaign_meta_row.get("eligible_campaign_types") or hypothesis_row.get("eligible_campaign_types")
                ),
                "preset_policy_state": _text((preset_policy_by_name.get(preset_name) or {}).get("policy_state")),
                "provenance_refs": _dedupe(
                    _normalize_sequence(registry_row.get("provenance_refs"))
                    + _normalize_sequence(operator_row.get("provenance_refs"))
                    + _normalize_sequence(why_row.get("provenance_refs"))
                    + _normalize_sequence(prior_failure_row.get("provenance_refs"))
                    + [
                        DEFAULT_SOURCE_USEFULNESS_PATH.as_posix(),
                        DEFAULT_SOURCE_IDENTITY_PATH.as_posix(),
                        DEFAULT_CACHE_PATH.as_posix(),
                        DEFAULT_HYPOTHESIS_CATALOG_PATH.as_posix(),
                        DEFAULT_CAMPAIGN_METADATA_PATH.as_posix(),
                        DEFAULT_TEMPLATES_PATH.as_posix(),
                        DEFAULT_PRESET_POLICY_PATH.as_posix(),
                        DEFAULT_CAMPAIGN_REGISTRY_PATH.as_posix(),
                        DEFAULT_SAMPLING_PLAN_PATH.as_posix(),
                        DEFAULT_MULTIWINDOW_RUN_PATH.as_posix(),
                        DEFAULT_BUDGET_PATH.as_posix(),
                        DEFAULT_PRESETS_SOURCE_PATH.as_posix(),
                    ],
                ),
                "authority_boundary": {
                    "read_only": True,
                    "context_only": True,
                    "can_authorize_execution": False,
                    "can_launch_campaign": False,
                    "can_generate_executable_strategy": False,
                    "can_promote_candidate": False,
                },
            }
            rows.append(cell)

    rows = sorted(rows, key=lambda row: (_text(row.get("source_hypothesis_id")), _text(row.get("preset_name")), _text(row.get("cell_id"))))
    status_counts = {
        status: sum(1 for row in rows if _text(row.get("inclusion_status")) == status)
        for status in VALID_INCLUSION_STATUSES
    }
    ready_cell_count = status_counts["READY_FOR_PREREGISTRATION"] + status_counts["READY_WITH_LIMITATIONS"]
    portfolio_identity = _portfolio_identity(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "portfolio_identity": portfolio_identity,
        "summary": {
            "cell_count": len(rows),
            "status_counts": status_counts,
            "ready_cell_count": ready_cell_count,
            "blocked_cell_count": status_counts["BLOCKED"],
            "insufficient_evidence_cell_count": status_counts["INSUFFICIENT_EVIDENCE"],
            "excluded_dead_zone_cell_count": status_counts["EXCLUDED_DEAD_ZONE"],
            "excluded_duplicate_cell_count": status_counts["EXCLUDED_DUPLICATE"],
            "final_recommendation": "no_executable_cells_visible" if ready_cell_count == 0 else "executable_cells_visible",
            "operator_summary": (
                "The portfolio plan is deterministic, read-only, fail-closed, and evidence-backed. "
                "It separates executable-ready cells from blocked or excluded scopes without inventing windows, trade counts, or execution authority."
            ),
        },
        "rows": rows,
        "artifact_references": {
            "qre_behavior_thesis_registry": DEFAULT_REGISTRY_PATH.as_posix(),
            "qre_operator_decision_report": DEFAULT_OPERATOR_REPORT_PATH.as_posix(),
            "qre_why_surfaces": DEFAULT_WHY_SURFACES_PATH.as_posix(),
            "qre_suppression_efficacy": DEFAULT_SUPPRESSION_PATH.as_posix(),
            "qre_experiment_dedup_novelty_enforcement": DEFAULT_DEDUP_PATH.as_posix(),
            "qre_research_cycle_router": DEFAULT_ROUTER_PATH.as_posix(),
            "qre_prior_failure_retrieval": DEFAULT_PRIOR_FAILURE_PATH.as_posix(),
            "qre_source_usefulness_ledger": DEFAULT_SOURCE_USEFULNESS_PATH.as_posix(),
            "qre_source_identity_authority_normalization": DEFAULT_SOURCE_IDENTITY_PATH.as_posix(),
            "qre_data_cache_manifest": DEFAULT_CACHE_PATH.as_posix(),
            "qre_evidence_breadth_framework": DEFAULT_BREADTH_PATH.as_posix(),
            "strategy_hypothesis_catalog": DEFAULT_HYPOTHESIS_CATALOG_PATH.as_posix(),
            "strategy_campaign_metadata": DEFAULT_CAMPAIGN_METADATA_PATH.as_posix(),
            "campaign_templates": DEFAULT_TEMPLATES_PATH.as_posix(),
            "preset_policy_state": DEFAULT_PRESET_POLICY_PATH.as_posix(),
            "campaign_registry": DEFAULT_CAMPAIGN_REGISTRY_PATH.as_posix(),
            "campaign_preregistered_sampling_plan": DEFAULT_SAMPLING_PLAN_PATH.as_posix(),
            "qre_preregistered_multiwindow_evidence_run": DEFAULT_MULTIWINDOW_RUN_PATH.as_posix(),
            "campaign_budget": DEFAULT_BUDGET_PATH.as_posix(),
            "presets_source": DEFAULT_PRESETS_SOURCE_PATH.as_posix(),
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "can_launch_campaign": False,
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "mutates_frozen_contracts": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Campaign Portfolio Plan",
        "",
        f"Generated by: `{MODULE_VERSION}`",
        f"Portfolio identity: `{_text(report.get('portfolio_identity'))}`",
        f"Final recommendation: `{_text((report.get('summary') or {}).get('final_recommendation'))}`",
        "",
        "| Thesis | Preset | Status | Next action |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("title")),
                    _text(row.get("preset_name")) or "thesis_only_gap",
                    _text(row.get("inclusion_status")),
                    _text(row.get("next_action")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_campaign_portfolio_plan.", suffix=".tmp", dir=str(path.parent))
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


def write_outputs(report: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path.cwd()
    latest = root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    latest_md = root / DEFAULT_OUTPUT_DIR / LATEST_MARKDOWN_NAME
    doc = root / DOC_PATH
    for target in (latest, latest_md, doc):
        _validate_write_target(target)
    _atomic_write(latest, json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown = render_markdown(report)
    _atomic_write(latest_md, markdown)
    _atomic_write(doc, markdown)
    return {
        "latest": latest.relative_to(root).as_posix(),
        "latest_md": latest_md.relative_to(root).as_posix(),
        "doc": DOC_PATH.as_posix(),
    }


def read_status(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    payload = _read_json(root / DEFAULT_OUTPUT_DIR / LATEST_NAME)
    if not payload:
        return {
            "status": "missing",
            "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
            "fails_closed": True,
        }
    return {
        "status": "ready",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_campaign_portfolio_plan",
        description="Materialize a deterministic, read-only QRE campaign portfolio plan.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_status(), indent=2, sort_keys=True))
        return 0
    report = build_campaign_portfolio_plan()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
