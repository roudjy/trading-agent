from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_routing_baseline_comparison"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017p-2026-06-26"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_routing_baseline_comparison")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_routing_baseline_comparison.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_routing_baseline_comparison/",
    "docs/governance/qre_routing_baseline_comparison.md",
)
DEFAULT_ROUTER_PATH: Final[Path] = Path("logs/qre_research_cycle_router/latest.json")
DEFAULT_OPPORTUNITY_PATH: Final[Path] = Path("logs/qre_opportunity_research_value/latest.json")

BASELINE_IDS: Final[tuple[str, ...]] = (
    "current_routing_score",
    "fifo_artifact_order",
    "lexical_direction_id",
    "lexical_behavior_id",
    "blocked_reason_count",
)
PRIORITY_BAND_VALUES: Final[frozenset[str]] = frozenset({"blocked", "low", "medium", "high", "missing"})
NEXT_ACTION_VALUES: Final[frozenset[str]] = frozenset(
    {
        "advance_to_routing_comparison",
        "increase_evidence_density",
        "resolve_data_readiness",
        "operator_review_context_only",
        "keep_fail_closed",
        "missing",
    }
)
FINAL_RECOMMENDATION: Final[str] = "routing_baseline_comparison_ready"
DIRECTION_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "direction_id",
    "behavior_id",
    "route_status",
    "artifact_index",
    "blocked_reason_count",
    "routing_score",
    "opportunity_score",
    "opportunity_priority_band",
    "opportunity_next_action",
    "decision_usefulness_proxy",
    "information_gain_proxy_score",
    "provenance_refs",
)
BASELINE_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "baseline_id",
    "ranking",
    "decision_usefulness_score",
    "top3_opportunity_capture",
    "top3_mean_information_gain_proxy",
    "top3_high_priority_count",
    "top3_data_ready_count",
    "top3_unique_behavior_count",
    "comparison_scope",
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


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_routing_baseline_comparison: refusing write outside allowlist: {path!r}"
        )


def _opportunity_index(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = _read_rows(payload, "rows")
    by_behavior: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        behavior = _text(row.get("behavior_family"))
        if behavior and behavior not in by_behavior:
            by_behavior[behavior] = {**dict(row), "_row_index": index}
    return by_behavior


def _direction_behavior_id(row: dict[str, Any]) -> str:
    return _text((row.get("target_hypothesis") or {}).get("behavior_id")) or _text(
        (row.get("proposed_scope") or {}).get("behavior_id")
    )


def _direction_record(
    row: dict[str, Any],
    *,
    index: int,
    opportunity_by_behavior: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    behavior_id = _direction_behavior_id(row)
    opportunity = opportunity_by_behavior.get(behavior_id, {})
    routing = dict(row.get("routing_context_only") or {})
    components = dict(routing.get("score_components") or {})
    opportunity_score = float(opportunity.get("opportunity_score") or 0.0)
    information_gain = float(components.get("information_gain_proxy_score") or 0.0)
    evidence_gap = float(components.get("evidence_gap_reduction_score") or 0.0)
    source_cache = float(components.get("source_cache_readiness_score") or 0.0)
    behavior_diversity = float(components.get("behavior_diversity_score") or 0.0)
    feasibility = float(components.get("feasibility_score") or 0.0)
    prior_penalty = float(components.get("prior_failure_penalty") or 0.0)
    compute_penalty = float(components.get("compute_cost_penalty") or 0.0)
    usefulness = max(
        0.0,
        min(
            1.0,
            (
                0.35 * opportunity_score
                + 0.20 * information_gain
                + 0.15 * evidence_gap
                + 0.10 * source_cache
                + 0.10 * behavior_diversity
                + 0.10 * feasibility
                - 0.10 * prior_penalty
                - 0.10 * compute_penalty
            ),
        ),
    )
    return {
        "direction_id": _text(row.get("direction_id")),
        "behavior_id": behavior_id,
        "route_status": _text(row.get("route_status")),
        "artifact_index": index,
        "blocked_reason_count": len(list(routing.get("blocked_reasons") or [])),
        "routing_score": float(routing.get("routing_score") or 0.0),
        "opportunity_score": round(opportunity_score, 6),
        "opportunity_priority_band": _text(opportunity.get("priority_band")) or "missing",
        "opportunity_next_action": _text(opportunity.get("recommended_next_action")) or "missing",
        "decision_usefulness_proxy": round(usefulness, 6),
        "information_gain_proxy_score": round(information_gain, 6),
        "provenance_refs": [
            f"{DEFAULT_ROUTER_PATH.as_posix()}#eligible_directions[{index}]",
            *(
                [f"{DEFAULT_OPPORTUNITY_PATH.as_posix()}#rows[{opportunity.get('_row_index')}]"]
                if "_row_index" in opportunity
                else []
            ),
        ],
    }


def _ranked(rows: list[dict[str, Any]], baseline_id: str) -> list[dict[str, Any]]:
    if baseline_id == "current_routing_score":
        return sorted(rows, key=lambda row: (-row["routing_score"], row["direction_id"]))
    if baseline_id == "fifo_artifact_order":
        return sorted(rows, key=lambda row: row["artifact_index"])
    if baseline_id == "lexical_direction_id":
        return sorted(rows, key=lambda row: row["direction_id"])
    if baseline_id == "lexical_behavior_id":
        return sorted(rows, key=lambda row: (row["behavior_id"], row["direction_id"]))
    if baseline_id == "blocked_reason_count":
        return sorted(rows, key=lambda row: (row["blocked_reason_count"], row["direction_id"]))
    raise KeyError(baseline_id)


def _dcg(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for index, row in enumerate(rows, start=1):
        discount = 1.0 / math.log2(index + 1)
        total += float(row["decision_usefulness_proxy"]) * discount
    return round(total, 6)


def _baseline_summary(baseline_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = _ranked(rows, baseline_id)
    top3 = ranked[:3]
    return {
        "baseline_id": baseline_id,
        "ranking": [row["direction_id"] for row in ranked],
        "decision_usefulness_score": _dcg(ranked),
        "top3_opportunity_capture": round(sum(float(row["opportunity_score"]) for row in top3), 6),
        "top3_mean_information_gain_proxy": round(
            sum(float(row["information_gain_proxy_score"]) for row in top3) / max(1, len(top3)),
            6,
        ),
        "top3_high_priority_count": sum(
            row["opportunity_priority_band"] in {"medium", "high"} for row in top3
        ),
        "top3_data_ready_count": sum(
            row["opportunity_next_action"] != "resolve_data_readiness" for row in top3
        ),
        "top3_unique_behavior_count": len({row["behavior_id"] for row in top3}),
        "comparison_scope": "context_only_not_execution_authority",
    }


def _source_status(payload: dict[str, Any] | None, *, required_field: str) -> dict[str, Any]:
    if payload is None:
        return {"status": "missing", "required_field": required_field, "fails_closed": True}
    if not isinstance(payload.get(required_field), list):
        return {"status": "invalid", "required_field": required_field, "fails_closed": True}
    return {"status": "ready", "required_field": required_field, "fails_closed": False}


def validate_direction(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    missing = [field for field in DIRECTION_REQUIRED_FIELDS if field not in row]
    if missing:
        reasons.append("missing_required_fields")
    if _text(row.get("opportunity_priority_band")) not in PRIORITY_BAND_VALUES:
        reasons.append("invalid_priority_band")
    if _text(row.get("opportunity_next_action")) not in NEXT_ACTION_VALUES:
        reasons.append("invalid_next_action")
    if not isinstance(row.get("provenance_refs"), list) or not row.get("provenance_refs"):
        reasons.append("missing_provenance_refs")
    for key in ("routing_score", "opportunity_score", "decision_usefulness_proxy", "information_gain_proxy_score"):
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            reasons.append(f"invalid_{key}")
            continue
        if not 0.0 <= value <= 1.0:
            reasons.append(f"out_of_range_{key}")
    return {"valid": not reasons, "rejection_reasons": reasons}


def validate_baseline(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    missing = [field for field in BASELINE_REQUIRED_FIELDS if field not in row]
    if missing:
        reasons.append("missing_required_fields")
    if _text(row.get("baseline_id")) not in BASELINE_IDS:
        reasons.append("invalid_baseline_id")
    if _text(row.get("comparison_scope")) != "context_only_not_execution_authority":
        reasons.append("invalid_comparison_scope")
    if not isinstance(row.get("ranking"), list):
        reasons.append("invalid_ranking")
    return {"valid": not reasons, "rejection_reasons": reasons}


def build_routing_baseline_comparison(
    *,
    repo_root: Path | None = None,
    router_report: dict[str, Any] | None = None,
    opportunity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    router_report = router_report or _read_json(root / DEFAULT_ROUTER_PATH)
    opportunity_report = opportunity_report or _read_json(root / DEFAULT_OPPORTUNITY_PATH)
    source_status = {
        "research_cycle_router": _source_status(router_report, required_field="eligible_directions"),
        "opportunity_research_value": _source_status(opportunity_report, required_field="rows"),
    }
    opportunity_by_behavior = _opportunity_index(opportunity_report)
    direction_rows = [
        _direction_record(row, index=index, opportunity_by_behavior=opportunity_by_behavior)
        for index, row in enumerate(_read_rows(router_report, "eligible_directions"))
    ]
    direction_rows.sort(key=lambda row: row["direction_id"])
    for row in direction_rows:
        validation = validate_direction(row)
        if not validation["valid"]:
            raise ValueError(
                "qre_routing_baseline_comparison: invalid direction row for "
                f"{row.get('direction_id')}: {validation['rejection_reasons']}"
            )
    baselines = [_baseline_summary(baseline_id, direction_rows) for baseline_id in BASELINE_IDS]
    baselines.sort(key=lambda row: (-float(row["decision_usefulness_score"]), row["baseline_id"]))
    for row in baselines:
        validation = validate_baseline(row)
        if not validation["valid"]:
            raise ValueError(
                "qre_routing_baseline_comparison: invalid baseline row for "
                f"{row.get('baseline_id')}: {validation['rejection_reasons']}"
            )
    current = next(row for row in baselines if row["baseline_id"] == "current_routing_score")
    best = baselines[0]
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "source_status": source_status,
        "artifact_references": {
            "research_cycle_router": DEFAULT_ROUTER_PATH.as_posix(),
            "opportunity_research_value": DEFAULT_OPPORTUNITY_PATH.as_posix(),
        },
        "directions": direction_rows,
        "baselines": baselines,
        "summary": {
            "direction_count": len(direction_rows),
            "baseline_count": len(baselines),
            "current_routing_score": current["decision_usefulness_score"],
            "best_baseline_id": best["baseline_id"],
            "best_baseline_score": best["decision_usefulness_score"],
            "current_minus_fifo": round(
                current["decision_usefulness_score"]
                - next(
                    row["decision_usefulness_score"]
                    for row in baselines
                    if row["baseline_id"] == "fifo_artifact_order"
                ),
                6,
            ),
            "final_recommendation": FINAL_RECOMMENDATION,
        },
        "safety_invariants": {
            "read_only": True,
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "context_only_not_authority": True,
        },
    }


def render_doc(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Routing Baseline Comparison",
        "",
        "This surface compares the current context-only router ordering against simple deterministic baselines.",
        "",
        "| baseline_id | usefulness | top3_opportunity_capture | top3_high_priority_count |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("baselines", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("baseline_id")),
                    f"{float(row.get('decision_usefulness_score') or 0.0):.3f}",
                    f"{float(row.get('top3_opportunity_capture') or 0.0):.3f}",
                    str(int(row.get("top3_high_priority_count") or 0)),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            f"- source router status: `{_text(((report.get('source_status') or {}).get('research_cycle_router') or {}).get('status'))}`",
            f"- source opportunity status: `{_text(((report.get('source_status') or {}).get('opportunity_research_value') or {}).get('status'))}`",
            "",
            "Current routing remains context only and does not authorize campaign execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path.cwd()
    latest = root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    doc = root / DOC_PATH
    latest.parent.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    for path in (latest, doc):
        _validate_write_target(path)
    tmp = latest.with_suffix(latest.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, latest)
    doc.write_text(render_doc(report), encoding="utf-8")
    return {
        "latest": latest.relative_to(root).as_posix(),
        "doc": doc.relative_to(root).as_posix(),
    }


def read_status(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    payload = _read_json(root / DEFAULT_OUTPUT_DIR / LATEST_NAME)
    if not payload:
        return {"status": "missing", "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(), "fails_closed": True}
    return {
        "status": "ready",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_status(), indent=2, sort_keys=True))
        return 0
    report = build_routing_baseline_comparison()
    if args.write:
        print(json.dumps(write_outputs(report), indent=2, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
