from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

from packages.qre_research import second_preregistered_campaign as campaign
from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-032.1"
EVIDENCE_PACK_PATH: Final[Path] = Path(
    "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json"
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{stable_digest(payload)[:16]}"


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".ade_qre_032.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_rows(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _registry_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("generated_strategy_id") or ""): row
        for row in _read_rows(
            repo_root / "generated_research" / "registry" / "generated_strategy_registry.v1.json"
        )
        if str(row.get("generated_strategy_id") or "")
    }


def _portfolio_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("campaign_cell_id") or ""): row
        for row in _read_rows(
            repo_root
            / "generated_research"
            / "readiness"
            / "campaigns"
            / "automated_portfolio_readiness.v1.json"
        )
        if str(row.get("campaign_cell_id") or "")
    }


def _spec_for_strategy(repo_root: Path, strategy_row: dict[str, Any]) -> dict[str, Any]:
    spec_id = str(strategy_row.get("strategy_spec_id") or "")
    if not spec_id:
        return {}
    spec_path = repo_root / "generated_research" / "specs" / f"{spec_id}.json"
    return _read_json(spec_path) if spec_path.is_file() else {}


def _extract_strategy_id(closeout: dict[str, Any]) -> str:
    decision = closeout.get("decision")
    if isinstance(decision, dict):
        failure_memory = decision.get("failure_memory_update")
        if isinstance(failure_memory, dict) and str(failure_memory.get("generated_strategy_id") or ""):
            return str(failure_memory.get("generated_strategy_id") or "")
    oos_consumption = closeout.get("oos_consumption")
    if isinstance(oos_consumption, dict) and str(oos_consumption.get("generated_strategy_id") or ""):
        return str(oos_consumption.get("generated_strategy_id") or "")
    return ""


def _extract_campaign_identity(closeout: dict[str, Any]) -> str:
    return str(closeout.get("executed_campaign_identity") or "")


def _stability_summary(train_stage: dict[str, Any], validation_stage: dict[str, Any], oos_stage: dict[str, Any]) -> dict[str, Any]:
    returns = [
        float(train_stage.get("net_return_compound") or 0.0),
        float(validation_stage.get("net_return_compound") or 0.0),
        float(oos_stage.get("net_return_compound") or 0.0),
    ]
    best_segment = max(returns)
    worst_segment = min(returns)
    dispersion = round(best_segment - worst_segment, 6)
    return {
        "status": "AVAILABLE",
        "best_segment_return": best_segment,
        "worst_segment_return": worst_segment,
        "dispersion": dispersion,
        "failure_concentration": "oos" if worst_segment == returns[-1] else "train_or_validation",
    }


def _outlier_dependency(stage: dict[str, Any]) -> dict[str, Any]:
    trades = list(stage.get("trades") or [])
    if not trades:
        return {"status": "UNKNOWN", "reason": "no_trade_records"}
    absolute_returns = [abs(float(item.get("net_return") or 0.0)) for item in trades]
    total = sum(absolute_returns)
    if total <= 0.0:
        return {"status": "UNKNOWN", "reason": "zero_absolute_trade_return"}
    dominant = max(absolute_returns)
    ratio = round(dominant / total, 6)
    return {
        "status": "AVAILABLE",
        "dominant_trade_fraction": ratio,
        "warning": "single_outlier_dependency_warning" if ratio >= 0.5 else "",
    }


def _disposition(closeout: dict[str, Any]) -> str:
    decision = closeout.get("decision")
    if not isinstance(decision, dict):
        return "NEEDS_MORE_EVIDENCE"
    hypothesis = str(decision.get("hypothesis_decision") or "")
    strategy = str(decision.get("strategy_decision") or "")
    if hypothesis == "SUPPORTED_FOR_FURTHER_RESEARCH" and strategy == "RESEARCH_SURVIVOR":
        return "READY_FOR_SYNTHESIS"
    if hypothesis == "BLOCKED_SAMPLE_SIZE":
        return "NEEDS_MORE_EVIDENCE"
    if hypothesis == "BLOCKED_CONTROLS":
        return "REQUIRES_PRIMITIVE_EXTENSION"
    if strategy.startswith("REJECTED"):
        return "REJECTED"
    return "NEEDS_MORE_EVIDENCE"


def build_empirical_evidence_pack(
    *,
    repo_root: Path = REPO_ROOT,
    closeout: dict[str, Any],
) -> dict[str, Any]:
    strategy_id = _extract_strategy_id(closeout)
    campaign_cell_id = str(closeout.get("executed_campaign_cell") or "")
    registry_row = _registry_index(repo_root).get(strategy_id, {})
    portfolio_row = _portfolio_index(repo_root).get(campaign_cell_id, {})
    spec = _spec_for_strategy(repo_root, registry_row)
    source_hypothesis_id = str(registry_row.get("source_hypothesis_id") or "")
    train_stage = dict(closeout.get("train_stage") or {})
    validation_stage = dict(closeout.get("validation_stage") or {})
    oos_stage = dict(closeout.get("oos_stage") or {})
    null_controls = dict(closeout.get("null_controls") or {})
    campaign_classification = dict(closeout.get("campaign_classification") or {})
    terminal_outcome = str(closeout.get("terminal_outcome") or "")
    disposition = _disposition(closeout)
    missing_evidence: list[str] = []
    if oos_stage.get("oos_outcome") != "COMPLETED":
        missing_evidence.append("oos_evidence")
    if not null_controls:
        missing_evidence.append("null_model_evidence")
    if float(oos_stage.get("costs") or 0.0) == 0.0:
        missing_evidence.append("transaction_cost_evidence")
    if not portfolio_row.get("train_window"):
        missing_evidence.append("sampling_window_evidence")
    contradiction_update = dict((closeout.get("decision") or {}).get("contradiction_update") or {})
    supporting_evidence: list[str] = []
    contradicting_evidence: list[str] = []
    if disposition == "READY_FOR_SYNTHESIS":
        supporting_evidence.append("campaign_survived_train_validation_oos_and_null_controls")
    else:
        contradicting_evidence.append(terminal_outcome or "campaign_not_supportive")
    contradiction_evidence = str(contradiction_update.get("evidence") or "")
    if contradiction_evidence:
        contradicting_evidence.append(contradiction_evidence)

    pack = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_evidence_pack",
        "evidence_pack_id": _content_id(
            "qep",
            {
                "campaign_cell_id": campaign_cell_id,
                "strategy_id": strategy_id,
                "terminal_outcome": terminal_outcome,
            },
        ),
        "source_hypothesis_id": source_hypothesis_id,
        "generated_strategy_id": strategy_id,
        "campaign_cell_id": campaign_cell_id,
        "campaign_identity": _extract_campaign_identity(closeout),
        "strategy_spec_id": str(registry_row.get("strategy_spec_id") or ""),
        "timeframe": str(portfolio_row.get("timeframe") or ""),
        "sample_boundaries": {
            "train_window": dict(portfolio_row.get("train_window") or {}),
            "validation_window": dict(portfolio_row.get("validation_window") or {}),
            "oos_window": dict(portfolio_row.get("oos_window") or {}),
        },
        "controlled_evaluation": {
            "status": "AVAILABLE",
            "train_stage": train_stage,
            "validation_stage": validation_stage,
            "oos_stage": oos_stage,
        },
        "walk_forward": {
            "status": "AVAILABLE",
            "segments": [
                {"stage": "train", "trade_count": int(train_stage.get("trade_count") or 0)},
                {"stage": "validation", "trade_count": int(validation_stage.get("trade_count") or 0)},
                {"stage": "oos", "trade_count": int(oos_stage.get("trade_count") or 0)},
            ],
        },
        "oos": {
            "status": "AVAILABLE" if oos_stage else "UNKNOWN",
            "outcome": str(oos_stage.get("oos_outcome") or ""),
            "trade_count": int(oos_stage.get("trade_count") or 0),
        },
        "transaction_costs": {
            "status": "AVAILABLE" if "cost_assumptions" in spec else "NOT_AVAILABLE",
            "assumptions": dict(spec.get("cost_assumptions") or {}),
            "realized_costs": float(oos_stage.get("costs") or 0.0),
        },
        "slippage": {
            "status": "AVAILABLE" if "slippage_assumptions" in spec else "NOT_AVAILABLE",
            "assumptions": dict(spec.get("slippage_assumptions") or {}),
            "realized_slippage": float(oos_stage.get("slippage") or 0.0),
        },
        "null_model": {
            "status": "AVAILABLE" if null_controls else "UNKNOWN",
            "passed": bool(null_controls.get("null_control_passed")),
            "rows": list(null_controls.get("rows") or []),
        },
        "stability": _stability_summary(train_stage, validation_stage, oos_stage),
        "regime_evidence": {
            "status": "NOT_AVAILABLE",
            "reason": "canonical_regime_segmentation_not_materialized_by_campaign_executor",
        },
        "parameter_fragility": {
            "status": (
                "NOT_AVAILABLE"
                if spec.get("parameters")
                else "NOT_APPLICABLE"
            ),
            "reason": (
                "bounded_parameter_sensitivity_not_run_in_campaign_executor"
                if spec.get("parameters")
                else "parameterless_behavior_test"
            ),
        },
        "outlier_dependency": _outlier_dependency(oos_stage),
        "campaign_classification": {
            "current_hypothesis_campaigns_executed": int(campaign_classification.get("current_hypothesis_campaigns_executed") or 0),
            "new_empirical_campaigns_completed": int(campaign_classification.get("new_empirical_campaigns_completed") or 0),
            "historical_campaigns_consumed": int(campaign_classification.get("historical_campaigns_consumed") or 0),
            "fixture_campaigns_consumed": int(campaign_classification.get("fixture_campaigns_consumed") or 0),
            "null_or_synthetic_campaigns_executed": int(campaign_classification.get("null_or_synthetic_campaigns_executed") or 0),
        },
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": contradicting_evidence,
        "campaign_refs": [
            "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
        ],
        "validation_refs": [
            str(registry_row.get("sandbox_validation_path") or ""),
        ],
        "missing_evidence": missing_evidence,
        "disposition": disposition,
        "terminal_outcome": terminal_outcome,
        "recommended_next_action": str(
            (closeout.get("feedback_routing") or {}).get("next_action")
            or "preserve_fail_closed_empirical_evidence"
        ),
    }
    return pack


def run_empirical_evidence_pack(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
    execute_if_missing: bool = True,
) -> dict[str, Any]:
    closeout_path = repo_root / "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json"
    if not closeout_path.is_file() and execute_if_missing:
        campaign.run_second_preregistered_campaign(repo_root=repo_root, write_outputs=write_outputs)
    closeout = _read_json(closeout_path)
    payload = build_empirical_evidence_pack(repo_root=repo_root, closeout=closeout)
    if write_outputs:
        _atomic_write(
            repo_root / EVIDENCE_PACK_PATH,
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
    return payload


__all__ = [
    "EVIDENCE_PACK_PATH",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "build_empirical_evidence_pack",
    "run_empirical_evidence_pack",
    "stable_digest",
]
