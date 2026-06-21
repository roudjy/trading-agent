"""Read-only campaign-level evidence materialization.

This module consolidates existing campaign registry, screening evidence,
research state, and action-plan artifacts. It does not launch campaigns or
change research policy, presets, gates, budgets, or strategies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

CAMPAIGN_LEVEL_EVIDENCE_SCHEMA_VERSION: Final[str] = "1.0"

DEFAULT_REPORT_JSON_PATH: Final[Path] = Path("research/campaign_level_evidence_latest.v1.json")
DEFAULT_REPORT_MD_PATH: Final[Path] = Path("research/campaign_level_evidence_latest.md")

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "campaign_registry": Path("research/campaign_registry_latest.v1.json"),
    "screening_evidence": Path("research/screening_evidence_latest.v1.json"),
    "research_state": Path("research/research_state_latest.v1.json"),
    "research_action_plan": Path("research/research_action_plan_latest.v1.json"),
    "campaign_evidence_ledger": Path("research/campaign_evidence_ledger_latest.v1.jsonl"),
}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    if not isinstance(payload, dict):
        return None, "malformed"
    return payload, "present"


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "missing"

    events: list[dict[str, Any]] = []
    malformed = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    malformed = True
                    continue
                if isinstance(item, dict):
                    events.append(item)
                else:
                    malformed = True
    except OSError:
        return [], "malformed"

    if malformed and not events:
        return [], "malformed"
    return events, "present"


def load_current_artifacts(
    *,
    root: Path = Path("."),
    artifact_paths: dict[str, Path] = ARTIFACT_PATHS,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    artifacts: dict[str, Any] = {}
    statuses: dict[str, dict[str, str]] = {}

    for name, relative_path in artifact_paths.items():
        path = root / relative_path
        if name == "campaign_evidence_ledger":
            payload, status = _read_jsonl(path)
        else:
            payload, status = _read_json(path)

        artifacts[name] = payload
        statuses[name] = {
            "path": relative_path.as_posix(),
            "status": status,
        }

    return artifacts, statuses


def _select_latest_completed_no_survivor(
    registry: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    campaigns = _dict_value(registry.get("campaigns"))

    eligible: list[tuple[str, dict[str, Any]]] = []
    for campaign_id, value in campaigns.items():
        record = _dict_value(value)
        if record.get("state") == "completed" and record.get("outcome") == "completed_no_survivor":
            eligible.append((str(campaign_id), record))

    if not eligible:
        return None, {}

    eligible.sort(
        key=lambda item: (
            str(item[1].get("finished_at_utc") or ""),
            item[0],
        ),
        reverse=True,
    )
    return eligible[0]


def _owned_screening_summary(
    screening: dict[str, Any],
    *,
    campaign_id: str,
) -> tuple[dict[str, Any], bool]:
    if not screening:
        return {}, False

    authoritative_owner = screening.get("col_campaign_id")
    if authoritative_owner is None:
        authoritative_owner = screening.get("campaign_id")

    if authoritative_owner is None or str(authoritative_owner) != campaign_id:
        return {}, False

    summary = screening.get("summary")
    if not isinstance(summary, dict):
        return {}, False

    return summary, True


def build_campaign_level_evidence_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()

    registry = _dict_value(artifacts.get("campaign_registry"))
    screening = _dict_value(artifacts.get("screening_evidence"))
    research_state = _dict_value(artifacts.get("research_state"))
    action_plan = _dict_value(artifacts.get("research_action_plan"))
    ledger_events = _list_value(artifacts.get("campaign_evidence_ledger"))

    campaign_id, record = _select_latest_completed_no_survivor(registry)

    if campaign_id is None:
        return {
            "schema_version": CAMPAIGN_LEVEL_EVIDENCE_SCHEMA_VERSION,
            "generated_at_utc": _iso_utc(generated),
            "artifact_inputs": artifact_status,
            "evidence_status": "unavailable",
            "campaign": None,
            "screening_evidence": None,
            "failure_attribution": _dict_value(research_state.get("failure_attribution")),
            "next_state_action": research_state.get("next_best_test"),
            "missing_or_malformed_artifacts": [
                name
                for name, status in artifact_status.items()
                if status.get("status") != "present"
            ],
            "safety_invariants": {
                "runs_campaign": False,
                "mutates_campaign_artifacts": False,
                "mutates_research_policy": False,
                "changes_presets_templates_or_gates": False,
                "paper_shadow_live_forbidden": True,
                "broker_risk_execution_forbidden": True,
            },
        }

    extra = _dict_value(record.get("extra"))
    gate_diagnostics = _dict_value(extra.get("gate_diagnostics"))

    screening_summary, owner_verified = _owned_screening_summary(
        screening,
        campaign_id=campaign_id,
    )

    counts_source = _dict_value(gate_diagnostics.get("counts"))
    if not counts_source and owner_verified:
        counts_source = screening_summary

    counts = {
        key: _safe_int(counts_source.get(key))
        for key in (
            "total_candidates",
            "passed_screening",
            "rejected_screening",
            "promotion_grade_candidates",
            "exploratory_passes",
            "near_passes",
            "sufficient_oos_evidence_candidates",
        )
    }

    failure_reasons = gate_diagnostics.get("dominant_failure_reasons")
    if not isinstance(failure_reasons, list) and owner_verified:
        failure_reasons = screening_summary.get("dominant_failure_reasons")
    dominant_failure_reasons = [str(item) for item in _list_value(failure_reasons)[:10]]

    campaign_events = [
        event for event in ledger_events if str(event.get("campaign_id") or "") == campaign_id
    ]

    missing_or_malformed = [
        name for name, status in artifact_status.items() if status.get("status") != "present"
    ]

    state_attribution = _dict_value(research_state.get("failure_attribution"))

    attributed = bool(gate_diagnostics or (owner_verified and state_attribution.get("attributed")))

    evidence_status = (
        "attributed_with_artifact_gaps"
        if attributed and missing_or_malformed
        else "attributed"
        if attributed
        else "incomplete_unattributed"
    )

    next_best_action = _dict_value(action_plan.get("next_best_action"))

    return {
        "schema_version": CAMPAIGN_LEVEL_EVIDENCE_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "artifact_inputs": artifact_status,
        "evidence_status": evidence_status,
        "campaign": {
            "campaign_id": campaign_id,
            "preset_name": record.get("preset_name"),
            "strategy_family": record.get("strategy_family"),
            "asset_class": record.get("asset_class"),
            "state": record.get("state"),
            "outcome": record.get("outcome"),
            "meaningful_classification": record.get("meaningful_classification"),
            "started_at_utc": record.get("started_at_utc"),
            "finished_at_utc": record.get("finished_at_utc"),
            "reason_code": record.get("reason_code"),
        },
        "screening_evidence": {
            "owner_verified": owner_verified,
            "classification": gate_diagnostics.get("classification"),
            "stage": gate_diagnostics.get("stage"),
            "source_run_id": gate_diagnostics.get("source_run_id") or screening.get("run_id"),
            "source_artifact_fingerprint": (
                gate_diagnostics.get("source_artifact_fingerprint")
                or screening.get("artifact_fingerprint")
            ),
            "counts": counts,
            "dominant_failure_reasons": dominant_failure_reasons,
        },
        "failure_attribution": _dict_value(research_state.get("failure_attribution")),
        "ledger_summary": {
            "campaign_event_count": len(campaign_events),
            "ledger_present": (artifact_status["campaign_evidence_ledger"]["status"] == "present"),
        },
        "current_decision_state": {
            "next_allowed_actions": _list_value(research_state.get("next_allowed_actions")),
            "next_best_test": research_state.get("next_best_test"),
            "action_plan_next_best_action": next_best_action.get("action_id"),
            "synthesis_gate": research_state.get("synthesis_gate"),
        },
        "missing_or_malformed_artifacts": missing_or_malformed,
        "interpretation": {
            "promotion_supported": counts["promotion_grade_candidates"] > 0,
            "primary_limitation": (
                dominant_failure_reasons[0] if dominant_failure_reasons else "unknown"
            ),
            "summary": (
                "Candidates passed initial screening but none reached " "promotion grade."
                if counts["passed_screening"] > 0 and counts["promotion_grade_candidates"] == 0
                else "Campaign-level evidence was consolidated."
            ),
        },
        "safety_invariants": {
            "runs_campaign": False,
            "mutates_campaign_artifacts": False,
            "mutates_research_policy": False,
            "changes_presets_templates_or_gates": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    campaign = _dict_value(payload.get("campaign"))
    screening = _dict_value(payload.get("screening_evidence"))
    counts = _dict_value(screening.get("counts"))
    decision = _dict_value(payload.get("current_decision_state"))
    interpretation = _dict_value(payload.get("interpretation"))

    lines = [
        "# Campaign-Level Evidence",
        "",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Evidence status: `{payload.get('evidence_status')}`",
        "",
        "## Campaign",
        f"- Campaign ID: `{campaign.get('campaign_id')}`",
        f"- Preset: `{campaign.get('preset_name')}`",
        f"- Outcome: `{campaign.get('outcome')}`",
        f"- Finished at UTC: `{campaign.get('finished_at_utc')}`",
        "",
        "## Screening And Promotion",
        f"- Owner verified: `{screening.get('owner_verified')}`",
        f"- Classification: `{screening.get('classification')}`",
        f"- Stage: `{screening.get('stage')}`",
        f"- Total candidates: {counts.get('total_candidates')}",
        f"- Passed screening: {counts.get('passed_screening')}",
        f"- Rejected screening: {counts.get('rejected_screening')}",
        ("- Promotion-grade candidates: " f"{counts.get('promotion_grade_candidates')}"),
        (
            "- Sufficient OOS evidence candidates: "
            f"{counts.get('sufficient_oos_evidence_candidates')}"
        ),
        (
            "- Dominant failure reasons: "
            f"{json.dumps(screening.get('dominant_failure_reasons') or [])}"
        ),
        "",
        "## Interpretation",
        f"- Primary limitation: `{interpretation.get('primary_limitation')}`",
        f"- Summary: {interpretation.get('summary')}",
        "",
        "## Current Decision State",
        ("- Next allowed actions: " f"{json.dumps(decision.get('next_allowed_actions') or [])}"),
        f"- Next best test: `{decision.get('next_best_test')}`",
        ("- Action-plan next action: " f"`{decision.get('action_plan_next_best_action')}`"),
        f"- Synthesis gate: `{decision.get('synthesis_gate')}`",
        "",
        "## Artifact Gaps",
        *[f"- `{name}`" for name in payload.get("missing_or_malformed_artifacts") or []],
        "",
    ]
    return "\n".join(lines)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def build_from_current_artifacts(
    *,
    root: Path = Path("."),
    report_json: Path = DEFAULT_REPORT_JSON_PATH,
    report_md: Path = DEFAULT_REPORT_MD_PATH,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    artifacts, statuses = load_current_artifacts(root=root)
    payload = build_campaign_level_evidence_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.campaign_level_evidence",
        description="Materialize read-only campaign-level research evidence.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read current QRE artifacts and write campaign evidence sidecars.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=DEFAULT_REPORT_JSON_PATH,
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=DEFAULT_REPORT_MD_PATH,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.from_current_artifacts:
        parser.error("--from-current-artifacts is required")

    payload = build_from_current_artifacts(
        report_json=args.report_json,
        report_md=args.report_md,
    )

    campaign = _dict_value(payload.get("campaign"))
    screening = _dict_value(payload.get("screening_evidence"))

    print(
        "campaign_level_evidence: "
        f"status={payload.get('evidence_status')} "
        f"campaign={campaign.get('campaign_id')} "
        f"classification={screening.get('classification')}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
