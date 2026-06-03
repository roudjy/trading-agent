"""Operator-facing QRE closed-loop completion report."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_operator_closed_loop_report"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_operator_closed_loop_report"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_operator_closed_loop_report/latest.json"
OUTPUT_MARKDOWN_RELATIVE_PATH: Final[str] = "logs/qre_operator_closed_loop_report/latest.md"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH
MARKDOWN_LATEST: Final[Path] = REPO_ROOT / OUTPUT_MARKDOWN_RELATIVE_PATH

DEFAULT_MARKET_OBSERVATIONS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_market_observations" / "latest.json"
)
DEFAULT_READINESS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_market_observation_hypothesis_readiness" / "latest.json"
)
DEFAULT_VALIDATION_REQUEST_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_executable_validation_request" / "latest.json"
)
DEFAULT_DRY_RUN_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_validation_request_dry_run" / "latest.json"
)
DEFAULT_CONTROLLED_REGENERATION_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_controlled_artifact_regeneration" / "latest.json"
)
DEFAULT_VALIDATION_RESULTS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_results" / "latest.json"
)
DEFAULT_EVIDENCE_QUALITY_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_evidence_quality_gate" / "latest.json"
)
DEFAULT_PROMOTION_INTENT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_validated_hypothesis_promotion_intent" / "latest.json"
)
DEFAULT_AUDIT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_post_run_evidence_promotion_audit" / "latest.json"
)
DEFAULT_SELECTION_ROUTE_VALIDATION_FLOW_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_selection_route_validation_flow" / "latest.json"
)
DEFAULT_SELECTION_CLOSED_LOOP_PREFLIGHT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_selection_closed_loop_preflight" / "latest.json"
)

LOOP_CLOSED_READY: Final[str] = "loop_closed_ready_for_operator_review"
LOOP_BLOCKED_IDENTITY: Final[str] = "loop_blocked_identity_missing"
LOOP_BLOCKED_NO_READY_REQUESTS: Final[str] = "loop_blocked_no_ready_requests"
LOOP_BLOCKED_NO_VALIDATION_RESULTS: Final[str] = "loop_blocked_no_validation_results"
LOOP_BLOCKED_EVIDENCE: Final[str] = "loop_blocked_evidence_insufficient"
LOOP_BLOCKED_PROMOTION: Final[str] = "loop_blocked_promotion_not_ready"
LOOP_REQUIRES_REGENERATION: Final[str] = "loop_requires_controlled_regeneration"


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
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _safe_counts(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    counts = payload.get("counts")
    return counts if isinstance(counts, dict) else {}


def _rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return []
    return rows


def _load(
    path: Path, *, expected_kind: str, label: str
) -> tuple[dict[str, Any] | None, dict[str, Any], list[str]]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return (None, meta, [f"{label}:missing_or_unparseable"])
    meta["valid"] = True
    return (payload, meta, [])


def _count_field(payload: dict[str, Any] | None, field: str) -> int:
    return len(_rows(payload, field))


def _loop_status(
    *,
    readiness: dict[str, Any] | None,
    requests: dict[str, Any] | None,
    dry_run: dict[str, Any] | None,
    controlled: dict[str, Any] | None,
    audit: dict[str, Any] | None,
) -> str:
    readiness_counts = _safe_counts(readiness)
    by_readiness = readiness.get("by_readiness_class", {}) if isinstance(readiness, dict) else {}
    request_counts = _safe_counts(requests)
    dry_counts = _safe_counts(dry_run)
    audit_recommendation = _bounded_str(
        audit.get("final_recommendation") if audit else "", max_len=120
    )
    if isinstance(by_readiness, dict) and by_readiness.get("execution_identity_missing", 0):
        return LOOP_BLOCKED_IDENTITY
    if audit_recommendation == "identity_route_still_blocked":
        return LOOP_BLOCKED_IDENTITY
    if controlled is None:
        return LOOP_REQUIRES_REGENERATION
    if request_counts.get("ready", 0) == 0 or dry_counts.get("ready", 0) == 0:
        return LOOP_BLOCKED_NO_READY_REQUESTS
    if audit_recommendation == "no_validation_results":
        return LOOP_BLOCKED_NO_VALIDATION_RESULTS
    if audit_recommendation in {
        "validation_results_present_but_insufficient",
        "evidence_quality_insufficient",
    }:
        return LOOP_BLOCKED_EVIDENCE
    if audit_recommendation == "promotion_not_ready":
        return LOOP_BLOCKED_PROMOTION
    if audit_recommendation == "promotion_ready_for_operator_review":
        return LOOP_CLOSED_READY
    if readiness_counts.get("hypothesis_ready", 0) == 0:
        return LOOP_BLOCKED_NO_READY_REQUESTS
    return LOOP_REQUIRES_REGENERATION


def _recommended_actions(loop_status: str, audit: dict[str, Any] | None) -> list[str]:
    audit_next = _bounded_str(audit.get("next_action") if audit else "", max_len=160)
    actions = {
        LOOP_BLOCKED_IDENTITY: ["repair_explicit_executable_identity_before_regeneration"],
        LOOP_REQUIRES_REGENERATION: [
            "run_controlled_regeneration_dry_run",
            "operator_decides_whether_reporting_only_materialization_is_allowed",
        ],
        LOOP_BLOCKED_NO_READY_REQUESTS: ["review_qre_validation_request_blockers"],
        LOOP_BLOCKED_NO_VALIDATION_RESULTS: [
            "operator_must_provide_or_generate_validation_results"
        ],
        LOOP_BLOCKED_EVIDENCE: ["collect_more_evidence_before_promotion_review"],
        LOOP_BLOCKED_PROMOTION: ["operator_review_or_more_evidence_required_before_promotion"],
        LOOP_CLOSED_READY: ["operator_review_promotion_intents"],
    }.get(loop_status, ["operator_review_required"])
    if audit_next and audit_next not in actions:
        actions.append(audit_next)
    return actions


def _operator_summary(
    *,
    observations: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
    requests: dict[str, Any] | None,
    dry_run: dict[str, Any] | None,
    controlled: dict[str, Any] | None,
    results: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    promotion: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    selection_route_validation_flow: dict[str, Any] | None = None,
    selection_closed_loop_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "market_observations": {
            "count": _count_field(observations, "observations"),
            "counts": _safe_counts(observations),
            "final_recommendation": _bounded_str(
                observations.get("final_recommendation") if observations else "", max_len=160
            ),
        },
        "hypothesis_readiness": {
            "counts": _safe_counts(readiness),
            "by_readiness_class": readiness.get("by_readiness_class", {})
            if isinstance(readiness, dict)
            else {},
            "final_recommendation": _bounded_str(
                readiness.get("final_recommendation") if readiness else "", max_len=160
            ),
        },
        "executable_validation_requests": {
            "counts": _safe_counts(requests),
            "final_recommendation": _bounded_str(
                requests.get("final_recommendation") if requests else "", max_len=160
            ),
        },
        "preset_strategy_eligibility": {
            "source": "qre_executable_validation_request.eligibility_status",
            "ready_requests": _safe_counts(requests).get("ready", 0),
            "blocked_requests": _safe_counts(requests).get("blocked", 0),
        },
        "dry_run_plans": {
            "counts": _safe_counts(dry_run),
            "executed_anything": dry_run.get("executed_anything") is True
            if isinstance(dry_run, dict)
            else False,
            "final_recommendation": _bounded_str(
                dry_run.get("final_recommendation") if dry_run else "", max_len=160
            ),
        },
        "controlled_regeneration": {
            "mode": _bounded_str(controlled.get("mode") if controlled else "", max_len=80),
            "backups_created_count": len(controlled.get("backups_created", []))
            if isinstance(controlled, dict)
            else 0,
            "executed_research_regeneration": controlled.get("executed_research_regeneration")
            is True
            if isinstance(controlled, dict)
            else False,
            "executed_reporting_materialization": controlled.get(
                "executed_reporting_materialization"
            )
            is True
            if isinstance(controlled, dict)
            else False,
            "final_recommendation": _bounded_str(
                controlled.get("final_recommendation") if controlled else "", max_len=160
            ),
        },
        "validation_results": {
            "count": _count_field(results, "validation_results"),
            "counts": _safe_counts(results),
        },
        "evidence_quality": {
            "rows": _count_field(evidence, "evidence_quality_rows"),
            "counts": _safe_counts(evidence),
        },
        "promotion_intent": {
            "rows": _count_field(promotion, "promotion_intents"),
            "counts": _safe_counts(promotion),
        },
        "selection_route": _selection_route_summary(
            selection_route_validation_flow,
            selection_closed_loop_preflight,
        ),
        "post_run_audit": {
            "final_recommendation": _bounded_str(
                audit.get("final_recommendation") if audit else "", max_len=160
            ),
            "next_action": _bounded_str(audit.get("next_action") if audit else "", max_len=160),
            "blockers": audit.get("blockers", []) if isinstance(audit, dict) else [],
        },
    }


def _selection_route_summary(
    selection_route_validation_flow: dict[str, Any] | None,
    selection_closed_loop_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    flow_counts = (
        selection_route_validation_flow.get("counts", {})
        if isinstance(selection_route_validation_flow, dict)
        else {}
    )
    preflight_route = (
        selection_closed_loop_preflight.get("selection_route", {})
        if isinstance(selection_closed_loop_preflight, dict)
        else {}
    )
    preflight_gate = (
        selection_closed_loop_preflight.get("controlled_regeneration_preflight", {})
        if isinstance(selection_closed_loop_preflight, dict)
        else {}
    )

    request_ready = int(flow_counts.get("request_ready_for_operator_review", 0) or 0)
    dry_run_ready = int(flow_counts.get("dry_run_ready", 0) or 0)
    route_ready = bool(preflight_route.get("ready"))
    can_consider_regeneration = bool(preflight_gate.get("can_be_considered"))

    return {
        "available": isinstance(selection_route_validation_flow, dict)
        and isinstance(selection_closed_loop_preflight, dict),
        "ready": route_ready,
        "counts": {
            "materialized_route_ready": int(flow_counts.get("materialized_route_ready", 0) or 0),
            "hypothesis_ready": int(flow_counts.get("hypothesis_ready", 0) or 0),
            "request_ready_for_operator_review": request_ready,
            "dry_run_ready": dry_run_ready,
            "selection_validation_flow_ready": int(
                flow_counts.get("selection_validation_flow_ready", 0) or 0
            ),
        },
        "controlled_regeneration_can_be_considered": can_consider_regeneration,
        "requires_operator_approval": bool(preflight_gate.get("requires_operator_approval", True)),
        "requires_backup_plan": bool(preflight_gate.get("requires_backup_plan", True)),
        "requires_explicit_regeneration_flag": bool(
            preflight_gate.get("requires_explicit_regeneration_flag", True)
        ),
        "final_recommendation": (
            selection_closed_loop_preflight.get("final_recommendation")
            if isinstance(selection_closed_loop_preflight, dict)
            else None
        ),
    }


def collect_snapshot(
    *,
    market_observations_path: Path | None = None,
    readiness_path: Path | None = None,
    validation_request_path: Path | None = None,
    dry_run_path: Path | None = None,
    controlled_regeneration_path: Path | None = None,
    validation_results_path: Path | None = None,
    evidence_quality_path: Path | None = None,
    promotion_intent_path: Path | None = None,
    audit_path: Path | None = None,
    selection_route_validation_flow_path: Path | None = None,
    selection_closed_loop_preflight_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    observations, meta_a, warnings_a = _load(
        market_observations_path or DEFAULT_MARKET_OBSERVATIONS_PATH,
        expected_kind="qre_market_observation_snapshot",
        label="market_observations",
    )
    readiness, meta_b, warnings_b = _load(
        readiness_path or DEFAULT_READINESS_PATH,
        expected_kind="qre_market_observation_hypothesis_readiness",
        label="readiness",
    )
    requests, meta_c, warnings_c = _load(
        validation_request_path or DEFAULT_VALIDATION_REQUEST_PATH,
        expected_kind="qre_executable_validation_request",
        label="validation_request",
    )
    dry_run, meta_d, warnings_d = _load(
        dry_run_path or DEFAULT_DRY_RUN_PATH,
        expected_kind="qre_validation_request_dry_run",
        label="dry_run",
    )
    controlled, meta_e, warnings_e = _load(
        controlled_regeneration_path or DEFAULT_CONTROLLED_REGENERATION_PATH,
        expected_kind="qre_controlled_artifact_regeneration",
        label="controlled_regeneration",
    )
    results, meta_f, warnings_f = _load(
        validation_results_path or DEFAULT_VALIDATION_RESULTS_PATH,
        expected_kind="qre_hypothesis_validation_results",
        label="validation_results",
    )
    evidence, meta_g, warnings_g = _load(
        evidence_quality_path or DEFAULT_EVIDENCE_QUALITY_PATH,
        expected_kind="qre_evidence_quality_gate",
        label="evidence_quality",
    )
    promotion, meta_h, warnings_h = _load(
        promotion_intent_path or DEFAULT_PROMOTION_INTENT_PATH,
        expected_kind="qre_validated_hypothesis_promotion_intent",
        label="promotion_intent",
    )
    audit, meta_i, warnings_i = _load(
        audit_path or DEFAULT_AUDIT_PATH,
        expected_kind="qre_post_run_evidence_promotion_audit",
        label="post_run_audit",
    )
    selection_route_validation_flow, meta_j, warnings_j = _load(
        selection_route_validation_flow_path or DEFAULT_SELECTION_ROUTE_VALIDATION_FLOW_PATH,
        expected_kind="qre_selection_route_validation_flow",
        label="selection_route_validation_flow",
    )
    selection_closed_loop_preflight, meta_k, warnings_k = _load(
        selection_closed_loop_preflight_path or DEFAULT_SELECTION_CLOSED_LOOP_PREFLIGHT_PATH,
        expected_kind="qre_selection_closed_loop_preflight",
        label="selection_closed_loop_preflight",
    )
    status = _loop_status(
        readiness=readiness,
        requests=requests,
        dry_run=dry_run,
        controlled=controlled,
        audit=audit,
    )
    summary = _operator_summary(
        observations=observations,
        readiness=readiness,
        requests=requests,
        dry_run=dry_run,
        controlled=controlled,
        results=results,
        evidence=evidence,
        promotion=promotion,
        audit=audit,
        selection_route_validation_flow=selection_route_validation_flow,
        selection_closed_loop_preflight=selection_closed_loop_preflight,
    )
    warnings = (
        warnings_a
        + warnings_b
        + warnings_c
        + warnings_d
        + warnings_e
        + warnings_f
        + warnings_g
        + warnings_h
        + warnings_i
        + warnings_j
        + warnings_k
    )
    actions = _recommended_actions(status, audit)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "safe_to_execute": False,
        "read_only": True,
        "final_recommendation": status,
        "loop_status": status,
        "operator_summary": summary,
        "recommended_actions": actions,
        "safety_summary": {
            "live_paper_shadow_broker_risk_execution_touched": False,
            "research_regeneration_executed": summary["controlled_regeneration"][
                "executed_research_regeneration"
            ],
            "reporting_materialization_executed": summary["controlled_regeneration"][
                "executed_reporting_materialization"
            ],
            "all_report_safe_to_execute_false": True,
            "operator_approval_required": True,
        },
        "artifact_refs": {
            "market_observations": meta_a,
            "hypothesis_readiness": meta_b,
            "validation_request": meta_c,
            "dry_run": meta_d,
            "controlled_regeneration": meta_e,
            "validation_results": meta_f,
            "evidence_quality": meta_g,
            "promotion_intent": meta_h,
            "post_run_audit": meta_i,
            "selection_route_validation_flow": meta_j,
            "selection_closed_loop_preflight": meta_k,
        },
        "blockers": summary["post_run_audit"]["blockers"] + warnings,
        "validation_warnings": warnings,
        "next_operator_action": actions[0],
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "launches_subprocess": False,
        "eligible_for_direct_execution": False,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("operator_summary", {})
    actions = snapshot.get("recommended_actions", [])
    blockers = snapshot.get("blockers", [])
    return "\n".join(
        [
            "# QRE Closed-Loop Operator Report",
            "",
            f"Generated: {snapshot.get('generated_at_utc')}",
            f"Loop status: {snapshot.get('loop_status')}",
            f"Final recommendation: {snapshot.get('final_recommendation')}",
            "",
            "## Route Summary",
            f"- Market observations: {summary.get('market_observations', {}).get('count', 0)}",
            f"- Ready validation requests: {summary.get('executable_validation_requests', {}).get('counts', {}).get('ready', 0)}",
            f"- Dry-run ready requests: {summary.get('dry_run_plans', {}).get('counts', {}).get('ready', 0)}",
            f"- Validation results: {summary.get('validation_results', {}).get('count', 0)}",
            f"- Evidence quality rows: {summary.get('evidence_quality', {}).get('rows', 0)}",
            f"- Promotion intents: {summary.get('promotion_intent', {}).get('rows', 0)}",
            "",
            "## Safety",
            "- safe_to_execute=false",
            "- No live, paper, shadow, broker, risk, or execution path is activated by this report.",
            "- Operator approval is required before any follow-up.",
            "",
            "## Blockers",
            *[f"- {item}" for item in blockers[:20]],
            "",
            "## Next Operator Actions",
            *[f"- {item}" for item in actions],
            "",
        ]
    )


def _atomic_write_text(path: Path, text: str, *, prefix: str) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE operator report dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=str(path.parent))
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
    markdown_path: Path | None = None,
) -> Path:
    json_target = output_path or ARTIFACT_LATEST
    md_target = markdown_path or MARKDOWN_LATEST
    _atomic_write_text(
        json_target,
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        prefix=".qre_operator_closed_loop_report.",
    )
    _atomic_write_text(
        md_target,
        render_markdown(snapshot),
        prefix=".qre_operator_closed_loop_report_md.",
    )
    return json_target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_operator_closed_loop_report",
        description="Build the operator-facing QRE closed-loop report.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--market-observations-source", type=Path, default=None)
    parser.add_argument("--readiness-source", type=Path, default=None)
    parser.add_argument("--validation-request-source", type=Path, default=None)
    parser.add_argument("--dry-run-source", type=Path, default=None)
    parser.add_argument("--controlled-regeneration-source", type=Path, default=None)
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--evidence-quality-source", type=Path, default=None)
    parser.add_argument("--promotion-intent-source", type=Path, default=None)
    parser.add_argument("--audit-source", type=Path, default=None)
    parser.add_argument("--selection-route-validation-flow-source", type=Path, default=None)
    parser.add_argument("--selection-closed-loop-preflight-source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        market_observations_path=args.market_observations_source,
        readiness_path=args.readiness_source,
        validation_request_path=args.validation_request_source,
        dry_run_path=args.dry_run_source,
        controlled_regeneration_path=args.controlled_regeneration_source,
        validation_results_path=args.results_source,
        evidence_quality_path=args.evidence_quality_source,
        promotion_intent_path=args.promotion_intent_source,
        audit_path=args.audit_source,
        selection_route_validation_flow_path=args.selection_route_validation_flow_source,
        selection_closed_loop_preflight_path=args.selection_closed_loop_preflight_source,
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
    "MARKDOWN_LATEST",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_MARKDOWN_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "render_markdown",
    "write_outputs",
]
