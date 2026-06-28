from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
REPORT_KIND: Final[str] = "qre_synthesis_readiness_review"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017ad-2026-06-28"

DEFAULT_MATURITY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_trusted_research_maturity_matrix" / "latest.json"
DEFAULT_EVIDENCE_DENSITY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_evidence_density_inventory" / "latest.json"
DEFAULT_REASON_MATURITY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_reason_record_maturity" / "latest.json"
DEFAULT_REASON_AUDIT_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_reason_record_audit" / "latest.json"
DEFAULT_ROUTING_BASELINE_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_routing_baseline_comparison" / "latest.json"
DEFAULT_ROUTING_SAMPLING_READINESS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_routing_sampling_readiness" / "latest.json"
DEFAULT_SAMPLING_BASELINE_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_sampling_baseline_comparison" / "latest.json"
DEFAULT_SUPPRESSION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_suppression_efficacy" / "latest.json"
DEFAULT_SOURCE_IDENTITY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_source_identity_authority_normalization" / "latest.json"
DEFAULT_SOURCE_USEFULNESS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_source_usefulness_ledger" / "latest.json"
DEFAULT_DATA_READINESS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_data_cache_manifest" / "latest.json"
DEFAULT_LINEAGE_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_contradiction_hypothesis_lineage" / "latest.json"
DEFAULT_DECAY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_evidence_decay" / "latest.json"
DEFAULT_OPERATOR_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_operator_decision_report" / "latest.json"
DEFAULT_WHY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_why_surfaces" / "latest.json"
DEFAULT_PORTFOLIO_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_campaign_portfolio_plan" / "latest.json"
DEFAULT_MANIFEST_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_preregistered_campaign_manifest" / "latest.json"
DEFAULT_EXECUTION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_execution" / "latest.json"
DEFAULT_DIAGNOSIS_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_broad_campaign_funnel_diagnosis" / "latest.json"
DEFAULT_RECALIBRATION_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_single_class_recalibration" / "latest.json"
DEFAULT_REPLAY_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_same_input_replay" / "latest.json"
DEFAULT_INDEPENDENT_PATH: Final[Path] = REPO_ROOT / "logs" / "qre_repeated_independent_oos" / "latest.json"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_synthesis_readiness_review"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = REPO_ROOT / "docs" / "governance" / "qre_synthesis_readiness_review.md"

WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_synthesis_readiness_review/",
    "docs/governance/qre_synthesis_readiness_review.md",
)
FINAL_DECISIONS: Final[tuple[str, ...]] = (
    "CONTINUE_BLOCKED",
    "ELIGIBLE_FOR_SEPARATE_SYNTHESIS_DESIGN_REVIEW",
    "INSUFFICIENT_EVIDENCE",
)
CRITERION_STATUSES: Final[tuple[str, ...]] = (
    "SATISFIED",
    "BLOCKED",
    "INSUFFICIENT_EVIDENCE",
)
THESIS_SYNTHESIS_STATES: Final[tuple[str, ...]] = (
    "REJECTED_NOT_SYNTHESIS_ELIGIBLE",
    "BLOCKED_PRE_SYNTHESIS",
)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get(field)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _stable_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_write_target(path: Path) -> None:
    normalized = _rel(path)
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _index_by(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _text(row.get(field))
        if key:
            indexed[key] = dict(row)
    return indexed


def _criterion(
    *,
    criterion_id: str,
    title: str,
    status: str,
    blocking_reason: str,
    evidence_refs: list[str],
    remediation_class: str,
    next_action: str,
    mandatory: bool = True,
) -> dict[str, Any]:
    if status not in CRITERION_STATUSES:
        raise ValueError(f"invalid criterion status: {status}")
    return {
        "criterion_id": criterion_id,
        "title": title,
        "status": status,
        "mandatory": mandatory,
        "satisfied": status == "SATISFIED",
        "blocking_reason": blocking_reason,
        "evidence_refs": evidence_refs,
        "remediation_class": remediation_class,
        "next_action": next_action,
    }


def _thesis_rows(operator: dict[str, Any], independent: dict[str, Any]) -> list[dict[str, Any]]:
    independent_by_hypothesis = _index_by(_rows(independent, "rows"), "source_hypothesis_id")
    rows: list[dict[str, Any]] = []
    for row in sorted(_rows(operator, "rows"), key=lambda item: _text(item.get("source_hypothesis_id"))):
        source_hypothesis_id = _text(row.get("source_hypothesis_id"))
        decision = _text(row.get("final_decision"))
        thesis_state = (
            "REJECTED_NOT_SYNTHESIS_ELIGIBLE"
            if decision == "REJECTED"
            else "BLOCKED_PRE_SYNTHESIS"
        )
        independent_row = independent_by_hypothesis.get(source_hypothesis_id, {})
        rows.append(
            {
                "source_hypothesis_id": source_hypothesis_id,
                "title": _text(row.get("title")),
                "final_decision": decision or "not_visible",
                "synthesis_state": thesis_state,
                "next_action": _text(row.get("next_action")) or "not_visible",
                "accepted_oos_count": _mapping(row.get("oos")).get("accepted_oos_count"),
                "independent_oos_status": _text(independent_row.get("independent_oos_status")) or "not_visible",
                "provenance_refs": _normalize_str_list(
                    [*list(row.get("provenance_refs") or []), _rel(DEFAULT_INDEPENDENT_PATH)]
                ),
            }
        )
    return rows


def _render_markdown(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    lines = [
        "# QRE Synthesis-Readiness Review",
        "",
        f"- synthesis_readiness_identity: `{_text(snapshot.get('synthesis_readiness_identity')) or 'not_materialized'}`",
        f"- final_readiness_outcome: `{_text(snapshot.get('final_readiness_outcome')) or 'not_visible'}`",
        f"- exact_next_permitted_action: `{_text(snapshot.get('exact_next_permitted_action')) or 'not_visible'}`",
        "",
        "## Blocking Summary",
        "",
        f"- mandatory_gate_count: `{summary.get('mandatory_gate_count', 0)}`",
        f"- failed_mandatory_gate_count: `{summary.get('failed_mandatory_gate_count', 0)}`",
        f"- passed_mandatory_gate_count: `{summary.get('passed_mandatory_gate_count', 0)}`",
        "",
        "## Failed Gates",
        "",
    ]
    for gate in summary.get("failed_mandatory_gates", []):
        lines.append(f"- `{gate}`")
    lines.extend(["", "## Thesis State", ""])
    for row in snapshot.get("thesis_rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{_text(row.get('source_hypothesis_id'))}`: `{_text(row.get('final_decision'))}` -> `{_text(row.get('next_action'))}`"
        )
    lines.extend(["", "## Remediation Backlog", ""])
    for row in snapshot.get("remediation_backlog", []):
        if not isinstance(row, dict):
            continue
        lines.append(f"- `{_text(row.get('priority'))}` `{_text(row.get('remediation_class'))}`: {_text(row.get('title'))}")
    return "\n".join(lines) + "\n"


def collect_snapshot(
    *,
    maturity_path: Path | None = None,
    evidence_density_path: Path | None = None,
    reason_maturity_path: Path | None = None,
    reason_audit_path: Path | None = None,
    routing_baseline_path: Path | None = None,
    routing_sampling_readiness_path: Path | None = None,
    sampling_baseline_path: Path | None = None,
    suppression_path: Path | None = None,
    source_identity_path: Path | None = None,
    source_usefulness_path: Path | None = None,
    data_readiness_path: Path | None = None,
    lineage_path: Path | None = None,
    decay_path: Path | None = None,
    operator_path: Path | None = None,
    why_path: Path | None = None,
    portfolio_path: Path | None = None,
    manifest_path: Path | None = None,
    execution_path: Path | None = None,
    diagnosis_path: Path | None = None,
    recalibration_path: Path | None = None,
    replay_path: Path | None = None,
    independent_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    maturity = _read_json(maturity_path or DEFAULT_MATURITY_PATH) or {}
    evidence_density = _read_json(evidence_density_path or DEFAULT_EVIDENCE_DENSITY_PATH) or {}
    reason_maturity = _read_json(reason_maturity_path or DEFAULT_REASON_MATURITY_PATH) or {}
    reason_audit = _read_json(reason_audit_path or DEFAULT_REASON_AUDIT_PATH) or {}
    routing_baseline = _read_json(routing_baseline_path or DEFAULT_ROUTING_BASELINE_PATH) or {}
    routing_sampling_readiness = _read_json(routing_sampling_readiness_path or DEFAULT_ROUTING_SAMPLING_READINESS_PATH) or {}
    sampling_baseline = _read_json(sampling_baseline_path or DEFAULT_SAMPLING_BASELINE_PATH) or {}
    suppression = _read_json(suppression_path or DEFAULT_SUPPRESSION_PATH) or {}
    source_identity = _read_json(source_identity_path or DEFAULT_SOURCE_IDENTITY_PATH) or {}
    source_usefulness = _read_json(source_usefulness_path or DEFAULT_SOURCE_USEFULNESS_PATH) or {}
    data_readiness = _read_json(data_readiness_path or DEFAULT_DATA_READINESS_PATH) or {}
    lineage = _read_json(lineage_path or DEFAULT_LINEAGE_PATH) or {}
    decay = _read_json(decay_path or DEFAULT_DECAY_PATH) or {}
    operator = _read_json(operator_path or DEFAULT_OPERATOR_PATH) or {}
    why = _read_json(why_path or DEFAULT_WHY_PATH) or {}
    portfolio = _read_json(portfolio_path or DEFAULT_PORTFOLIO_PATH) or {}
    manifest = _read_json(manifest_path or DEFAULT_MANIFEST_PATH) or {}
    execution = _read_json(execution_path or DEFAULT_EXECUTION_PATH) or {}
    diagnosis = _read_json(diagnosis_path or DEFAULT_DIAGNOSIS_PATH) or {}
    recalibration = _read_json(recalibration_path or DEFAULT_RECALIBRATION_PATH) or {}
    replay = _read_json(replay_path or DEFAULT_REPLAY_PATH) or {}
    independent = _read_json(independent_path or DEFAULT_INDEPENDENT_PATH) or {}
    generated = generated_at_utc or _utcnow()

    maturity_summary = _mapping(maturity.get("summary"))
    evidence_summary = _mapping(evidence_density.get("summary"))
    reason_maturity_summary = _mapping(reason_maturity.get("summary"))
    reason_audit_summary = _mapping(reason_audit.get("summary"))
    routing_baseline_summary = _mapping(routing_baseline.get("summary"))
    readiness_summary = _mapping(routing_sampling_readiness.get("summary"))
    sampling_baseline_summary = _mapping(sampling_baseline.get("summary"))
    suppression_summary = _mapping(suppression.get("summary"))
    source_identity_summary = _mapping(source_identity.get("summary"))
    source_usefulness_summary = _mapping(source_usefulness.get("summary"))
    data_summary = _mapping(data_readiness.get("summary"))
    lineage_summary = _mapping(lineage.get("summary"))
    decay_summary = _mapping(decay.get("summary"))
    operator_summary = _mapping(operator.get("summary"))
    portfolio_summary = _mapping(portfolio.get("summary"))
    manifest_summary = _mapping(manifest.get("summary"))
    execution_summary = _mapping(execution.get("summary"))
    diagnosis_summary = _mapping(diagnosis.get("summary"))
    diagnosis_counts = _mapping(diagnosis.get("funnel_counts"))
    recalibration_summary = _mapping(recalibration.get("summary"))
    replay_summary = _mapping(replay.get("summary"))
    independent_summary = _mapping(independent.get("summary"))

    criteria = [
        _criterion(
            criterion_id="evidence_density_maturity",
            title="Evidence density maturity",
            status="BLOCKED" if int(maturity_summary.get("evidence_authoritative_surface_count") or 0) == 0 else "SATISFIED",
            blocking_reason="No evidence-authoritative maturity surfaces are materialized; overall baseline remains mixed decision-useful pockets, not operator-trusted.",
            evidence_refs=[_rel(DEFAULT_MATURITY_PATH), _rel(DEFAULT_EVIDENCE_DENSITY_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="raise evidence classes from partial/thin to operator-trusted coverage",
        ),
        _criterion(
            criterion_id="reason_record_completeness",
            title="Reason-record completeness",
            status="BLOCKED" if int(reason_audit_summary.get("reason_records_manifest_total") or 0) == 0 else "SATISFIED",
            blocking_reason="Reason-record audit still reports an empty manifest total and contract gaps before authority upgrade.",
            evidence_refs=[_rel(DEFAULT_REASON_MATURITY_PATH), _rel(DEFAULT_REASON_AUDIT_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="normalize reason-record contract gaps before authority upgrade",
        ),
        _criterion(
            criterion_id="routing_usefulness",
            title="Routing usefulness",
            status="SATISFIED" if int(readiness_summary.get("routing_ready_count") or 0) > 0 else "BLOCKED",
            blocking_reason="" if int(readiness_summary.get("routing_ready_count") or 0) > 0 else "No evidence-backed routing-ready items are materialized.",
            evidence_refs=[_rel(DEFAULT_ROUTING_BASELINE_PATH), _rel(DEFAULT_ROUTING_SAMPLING_READINESS_PATH)],
            remediation_class="no_remediation_required" if int(readiness_summary.get("routing_ready_count") or 0) > 0 else "evidence_completeness_population",
            next_action="preserve_evidence_backed_ready_and_non_ready_states" if int(readiness_summary.get("routing_ready_count") or 0) > 0 else "materialize evidence-backed routing-ready items",
        ),
        _criterion(
            criterion_id="sampling_usefulness",
            title="Sampling usefulness",
            status="SATISFIED" if int(readiness_summary.get("sampling_ready_count") or 0) > 0 else "BLOCKED",
            blocking_reason="" if int(readiness_summary.get("sampling_ready_count") or 0) > 0 else "No evidence-backed sampling-ready items are materialized.",
            evidence_refs=[_rel(DEFAULT_SAMPLING_BASELINE_PATH), _rel(DEFAULT_ROUTING_SAMPLING_READINESS_PATH)],
            remediation_class="no_remediation_required" if int(readiness_summary.get("sampling_ready_count") or 0) > 0 else "evidence_completeness_population",
            next_action="preserve_evidence_backed_ready_and_non_ready_states" if int(readiness_summary.get("sampling_ready_count") or 0) > 0 else "materialize evidence-backed sampling-ready items",
        ),
        _criterion(
            criterion_id="suppression_usefulness",
            title="Suppression usefulness",
            status="BLOCKED",
            blocking_reason="Suppression mechanics are visible, but the repo still lacks a valid same-population no-suppression baseline to prove usefulness.",
            evidence_refs=[_rel(DEFAULT_SUPPRESSION_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="materialize same-population suppression comparator evidence",
        ),
        _criterion(
            criterion_id="source_quality",
            title="Source quality",
            status="SATISFIED" if bool(source_usefulness_summary.get("source_quality_ready")) else "BLOCKED",
            blocking_reason="" if bool(source_usefulness_summary.get("source_quality_ready")) else "Source quality is not ready for current bounded research scope.",
            evidence_refs=[_rel(DEFAULT_SOURCE_USEFULNESS_PATH)],
            remediation_class="no_remediation_required" if bool(source_usefulness_summary.get("source_quality_ready")) else "data_source_readiness",
            next_action="preserve_current_source_quality_gate" if bool(source_usefulness_summary.get("source_quality_ready")) else "raise source quality readiness to research-ready",
        ),
        _criterion(
            criterion_id="data_readiness",
            title="Data readiness",
            status="SATISFIED" if bool(data_summary.get("research_ready")) else "BLOCKED",
            blocking_reason="" if bool(data_summary.get("research_ready")) else "Campaign-ready cache/data readiness is not established.",
            evidence_refs=[_rel(DEFAULT_DATA_READINESS_PATH)],
            remediation_class="no_remediation_required" if bool(data_summary.get("research_ready")) else "data_source_readiness",
            next_action="preserve current data cache readiness" if bool(data_summary.get("research_ready")) else "materialize campaign-ready cache/data readiness",
        ),
        _criterion(
            criterion_id="identity_readiness",
            title="Identity readiness",
            status="BLOCKED" if int(source_identity_summary.get("blocked_scope_count") or 0) > 0 else "SATISFIED",
            blocking_reason="Identity normalization still reports blocked or ambiguous scopes, so synthesis cannot treat identity as resolved.",
            evidence_refs=[_rel(DEFAULT_SOURCE_IDENTITY_PATH), _rel(DEFAULT_DIAGNOSIS_PATH)],
            remediation_class="identity_ambiguity_resolution",
            next_action="materialize identity inventory for bounded scope",
        ),
        _criterion(
            criterion_id="campaign_lineage_completeness",
            title="Campaign lineage completeness",
            status="BLOCKED" if int(lineage_summary.get("missing_lineage_count") or 0) > 0 else "SATISFIED",
            blocking_reason="Six theses still lack campaign lineage, leaving campaign and funnel references incomplete.",
            evidence_refs=[_rel(DEFAULT_LINEAGE_PATH), _rel(DEFAULT_OPERATOR_PATH)],
            remediation_class="campaign_lineage_establishment",
            next_action="establish campaign lineage for blocked theses",
        ),
        _criterion(
            criterion_id="hypothesis_lineage_completeness",
            title="Hypothesis lineage completeness",
            status="BLOCKED" if int(lineage_summary.get("complete_lineage_count") or 0) < int(operator_summary.get("thesis_count") or 0) else "SATISFIED",
            blocking_reason="Only one thesis has complete lineage; the rest remain orphaned or incomplete.",
            evidence_refs=[_rel(DEFAULT_LINEAGE_PATH)],
            remediation_class="campaign_lineage_establishment",
            next_action="complete hypothesis lineage for remaining blocked theses",
        ),
        _criterion(
            criterion_id="contradiction_visibility",
            title="Contradiction visibility",
            status="SATISFIED" if int(lineage_summary.get("contradiction_visible_count") or 0) == int(operator_summary.get("thesis_count") or 0) else "BLOCKED",
            blocking_reason="" if int(lineage_summary.get("contradiction_visible_count") or 0) == int(operator_summary.get("thesis_count") or 0) else "Contradictions are not visible for the full thesis set.",
            evidence_refs=[_rel(DEFAULT_LINEAGE_PATH), _rel(DEFAULT_DECAY_PATH)],
            remediation_class="no_remediation_required" if int(lineage_summary.get("contradiction_visible_count") or 0) == int(operator_summary.get("thesis_count") or 0) else "evidence_completeness_population",
            next_action="preserve visible contradiction surfaces" if int(lineage_summary.get("contradiction_visible_count") or 0) == int(operator_summary.get("thesis_count") or 0) else "materialize missing contradiction visibility",
        ),
        _criterion(
            criterion_id="reproducibility",
            title="Reproducibility",
            status="BLOCKED" if int(decay_summary.get("blocked_count") or 0) > 0 else "SATISFIED",
            blocking_reason="Evidence decay still blocks every thesis due to unreproducible, stale, contradicted, or incomplete evidence.",
            evidence_refs=[_rel(DEFAULT_DECAY_PATH), _rel(DEFAULT_OPERATOR_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="repair reproducibility blockers before any synthesis review",
        ),
        _criterion(
            criterion_id="evidence_freshness",
            title="Evidence freshness",
            status="BLOCKED" if int(decay_summary.get("blocked_count") or 0) > 0 else "SATISFIED",
            blocking_reason="Decay keeps stale or superseded artifacts from supporting readiness; no thesis is clear.",
            evidence_refs=[_rel(DEFAULT_DECAY_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="renew stale or superseded evidence with authoritative updates",
        ),
        _criterion(
            criterion_id="accepted_oos",
            title="Accepted OOS",
            status="BLOCKED" if int(diagnosis_counts.get("oos_accepted_count") or 0) == 0 else "SATISFIED",
            blocking_reason="The authoritative campaign funnel shows zero accepted OOS.",
            evidence_refs=[_rel(DEFAULT_EXECUTION_PATH), _rel(DEFAULT_DIAGNOSIS_PATH), _rel(DEFAULT_OPERATOR_PATH)],
            remediation_class="replacement_hypothesis_planning" if int(diagnosis_counts.get("oos_accepted_count") or 0) == 0 else "no_remediation_required",
            next_action="replace rejected hypothesis planning and re-establish campaign-ready evidence",
        ),
        _criterion(
            criterion_id="repeated_independent_oos",
            title="Repeated independent OOS",
            status="BLOCKED" if int(independent_summary.get("independent_ready_count") or 0) == 0 else "SATISFIED",
            blocking_reason="No valid unseen independent OOS path is materialized.",
            evidence_refs=[_rel(DEFAULT_INDEPENDENT_PATH)],
            remediation_class="independent_oos_capacity",
            next_action="create new campaign-ready unseen independent window capacity before repetition",
        ),
        _criterion(
            criterion_id="null_control_completeness",
            title="Null-control completeness",
            status="BLOCKED" if int(diagnosis_counts.get("null_control_complete_count") or 0) == 0 else "SATISFIED",
            blocking_reason="No thesis has complete null controls; the only campaign-backed thesis still lacks the preregistered holdout control.",
            evidence_refs=[_rel(DEFAULT_EXECUTION_PATH), _rel(DEFAULT_DIAGNOSIS_PATH), _rel(DEFAULT_INDEPENDENT_PATH)],
            remediation_class="null_control_completion",
            next_action="materialize missing preregistered null controls",
        ),
        _criterion(
            criterion_id="validation_completeness",
            title="Validation completeness",
            status="BLOCKED" if int(diagnosis_counts.get("validation_completed_count") or 0) == 0 else "SATISFIED",
            blocking_reason="The broad funnel records zero validation-complete scopes.",
            evidence_refs=[_rel(DEFAULT_DIAGNOSIS_PATH), _rel(DEFAULT_EXECUTION_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="materialize validation-complete campaign scopes",
        ),
        _criterion(
            criterion_id="operator_decision_report_completeness",
            title="Operator decision-report completeness",
            status="BLOCKED" if int(maturity_summary.get("operator_trusted_surface_count") or 0) == 0 else "SATISFIED",
            blocking_reason="Operator decision reports are present but not operator-trusted readiness evidence for synthesis.",
            evidence_refs=[_rel(DEFAULT_OPERATOR_PATH), _rel(DEFAULT_MATURITY_PATH), _rel(DEFAULT_WHY_PATH)],
            remediation_class="evidence_completeness_population",
            next_action="raise operator decision surfaces to operator-trusted evidence quality",
        ),
        _criterion(
            criterion_id="evidence_authority_ambiguity_absent",
            title="Absence of unresolved evidence-authority ambiguity",
            status="BLOCKED" if int(source_identity_summary.get("blocked_scope_count") or 0) > 0 else "SATISFIED",
            blocking_reason="Source identity authority normalization still exposes unresolved or blocked identity authority states.",
            evidence_refs=[_rel(DEFAULT_SOURCE_IDENTITY_PATH), _rel(DEFAULT_MATURITY_PATH)],
            remediation_class="identity_ambiguity_resolution",
            next_action="resolve blocked identity authority scopes",
        ),
        _criterion(
            criterion_id="trading_authority_leakage_absent",
            title="Absence of trading-authority leakage",
            status="SATISFIED",
            blocking_reason="",
            evidence_refs=[
                _rel(DEFAULT_OPERATOR_PATH),
                _rel(DEFAULT_PORTFOLIO_PATH),
                _rel(DEFAULT_MANIFEST_PATH),
                _rel(DEFAULT_EXECUTION_PATH),
                _rel(DEFAULT_REPLAY_PATH),
                _rel(DEFAULT_INDEPENDENT_PATH),
            ],
            remediation_class="no_remediation_required",
            next_action="preserve read-only review boundary",
        ),
    ]

    failed_mandatory = [row["criterion_id"] for row in criteria if row["mandatory"] and not row["satisfied"]]
    passed_mandatory = [row["criterion_id"] for row in criteria if row["mandatory"] and row["satisfied"]]

    supported_for_review_count = int(_mapping(operator_summary.get("decision_counts")).get("SUPPORTED_FOR_REVIEW") or 0)
    if any(row["status"] == "INSUFFICIENT_EVIDENCE" for row in criteria) and not failed_mandatory:
        final_outcome = "INSUFFICIENT_EVIDENCE"
    elif failed_mandatory or supported_for_review_count == 0:
        final_outcome = "CONTINUE_BLOCKED"
    else:
        final_outcome = "ELIGIBLE_FOR_SEPARATE_SYNTHESIS_DESIGN_REVIEW"

    thesis_rows = _thesis_rows(operator, independent)
    remediation_backlog = [
        {
            "priority": 1,
            "remediation_class": "campaign_lineage_establishment",
            "title": "Establish campaign lineage for the six blocked theses",
            "why_now": "Six theses remain blocked before campaign lineage, which keeps both hypothesis and campaign lineage gates open.",
            "evidence_refs": [_rel(DEFAULT_LINEAGE_PATH), _rel(DEFAULT_OPERATOR_PATH)],
        },
        {
            "priority": 2,
            "remediation_class": "identity_ambiguity_resolution",
            "title": "Resolve source and instrument identity ambiguity",
            "why_now": "Identity authority still reports blocked scopes and is a mandatory synthesis gate.",
            "evidence_refs": [_rel(DEFAULT_SOURCE_IDENTITY_PATH), _rel(DEFAULT_DIAGNOSIS_PATH)],
        },
        {
            "priority": 3,
            "remediation_class": "null_control_completion",
            "title": "Complete preregistered null controls",
            "why_now": "Null-control completeness is zero and blocks the only campaign-backed thesis from advancing.",
            "evidence_refs": [_rel(DEFAULT_EXECUTION_PATH), _rel(DEFAULT_INDEPENDENT_PATH)],
        },
        {
            "priority": 4,
            "remediation_class": "evidence_completeness_population",
            "title": "Populate evidence-completeness gaps across validation, reproducibility, and operator-trust surfaces",
            "why_now": "Evidence completeness is the primary funnel bottleneck and still blocks every thesis via decay.",
            "evidence_refs": [_rel(DEFAULT_DIAGNOSIS_PATH), _rel(DEFAULT_DECAY_PATH), _rel(DEFAULT_MATURITY_PATH)],
        },
        {
            "priority": 5,
            "remediation_class": "data_source_readiness",
            "title": "Expand campaign-ready data and unseen-window capacity",
            "why_now": "Current cache/source readiness is only sufficient for the existing bounded scope and does not create new independent OOS capacity.",
            "evidence_refs": [_rel(DEFAULT_DATA_READINESS_PATH), _rel(DEFAULT_INDEPENDENT_PATH)],
        },
        {
            "priority": 6,
            "remediation_class": "independent_oos_capacity",
            "title": "Create valid independent OOS capacity",
            "why_now": "Repeated independent OOS is blocked because no unseen valid window is materialized.",
            "evidence_refs": [_rel(DEFAULT_INDEPENDENT_PATH), _rel(DEFAULT_REPLAY_PATH)],
        },
        {
            "priority": 7,
            "remediation_class": "replacement_hypothesis_planning",
            "title": "Plan replacement hypotheses for rejected trend_pullback_v1",
            "why_now": "The only campaign-backed thesis is already fail-closed rejected and cannot be promoted into synthesis.",
            "evidence_refs": [_rel(DEFAULT_OPERATOR_PATH), _rel(DEFAULT_INDEPENDENT_PATH)],
        },
        {
            "priority": 8,
            "remediation_class": "second_broad_preregistered_campaign",
            "title": "Run a second broad preregistered campaign only after the blocked gates are repaired",
            "why_now": "A new campaign is needed for new authoritative evidence, but only after lineage, identity, controls, and capacity blockers are repaired.",
            "evidence_refs": [_rel(DEFAULT_PORTFOLIO_PATH), _rel(DEFAULT_MANIFEST_PATH), _rel(DEFAULT_EXECUTION_PATH)],
        },
        {
            "priority": 9,
            "remediation_class": "synthesis_design",
            "title": "Re-run synthesis-readiness review before any separate synthesis design review",
            "why_now": "Synthesis design must remain last and blocked until all mandatory readiness gates are satisfied.",
            "evidence_refs": [_rel(DOC_PATH)],
        },
    ]

    exact_next_permitted_action = "launch_separate_remediation_program_for_lineage_identity_controls_evidence_and_capacity_before_any_synthesis_design_review"
    identity_seed = {
        "portfolio_identity": _text(portfolio.get("portfolio_identity")),
        "manifest_identity": _text(manifest.get("manifest_identity")),
        "execution_identity": _text(execution.get("campaign_execution_identity")),
        "diagnosis_identity": _text(diagnosis.get("diagnosis_identity")),
        "recalibration_identity": _text(recalibration.get("recalibration_identity")),
        "replay_identity": _text(replay.get("replay_assessment_identity")),
        "independent_identity": _text(independent.get("independent_oos_identity")),
        "final_outcome": final_outcome,
        "failed_mandatory": failed_mandatory,
    }

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "artifact_references": {
            "governance_doc": _rel(DOC_PATH),
            "qre_trusted_research_maturity_matrix": _rel(DEFAULT_MATURITY_PATH),
            "qre_evidence_density_inventory": _rel(DEFAULT_EVIDENCE_DENSITY_PATH),
            "qre_reason_record_maturity": _rel(DEFAULT_REASON_MATURITY_PATH),
            "qre_reason_record_audit": _rel(DEFAULT_REASON_AUDIT_PATH),
            "qre_routing_baseline_comparison": _rel(DEFAULT_ROUTING_BASELINE_PATH),
            "qre_routing_sampling_readiness": _rel(DEFAULT_ROUTING_SAMPLING_READINESS_PATH),
            "qre_sampling_baseline_comparison": _rel(DEFAULT_SAMPLING_BASELINE_PATH),
            "qre_suppression_efficacy": _rel(DEFAULT_SUPPRESSION_PATH),
            "qre_source_identity_authority_normalization": _rel(DEFAULT_SOURCE_IDENTITY_PATH),
            "qre_source_usefulness_ledger": _rel(DEFAULT_SOURCE_USEFULNESS_PATH),
            "qre_data_cache_manifest": _rel(DEFAULT_DATA_READINESS_PATH),
            "qre_contradiction_hypothesis_lineage": _rel(DEFAULT_LINEAGE_PATH),
            "qre_evidence_decay": _rel(DEFAULT_DECAY_PATH),
            "qre_operator_decision_report": _rel(DEFAULT_OPERATOR_PATH),
            "qre_why_surfaces": _rel(DEFAULT_WHY_PATH),
            "qre_campaign_portfolio_plan": _rel(DEFAULT_PORTFOLIO_PATH),
            "qre_preregistered_campaign_manifest": _rel(DEFAULT_MANIFEST_PATH),
            "qre_broad_campaign_execution": _rel(DEFAULT_EXECUTION_PATH),
            "qre_broad_campaign_funnel_diagnosis": _rel(DEFAULT_DIAGNOSIS_PATH),
            "qre_single_class_recalibration": _rel(DEFAULT_RECALIBRATION_PATH),
            "qre_same_input_replay": _rel(DEFAULT_REPLAY_PATH),
            "qre_repeated_independent_oos": _rel(DEFAULT_INDEPENDENT_PATH),
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_launch_campaign": False,
            "can_authorize_execution": False,
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_activate_paper_shadow_live": False,
        },
        "safety_invariants": {
            "mutates_campaign_results": False,
            "mutates_thresholds": False,
            "mutates_frozen_contracts": False,
            "strategy_synthesis_implemented": False,
            "strategy_registration_enabled": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "source_identities": {
            "portfolio_identity": _text(portfolio.get("portfolio_identity")),
            "manifest_identity": _text(manifest.get("manifest_identity")),
            "replay_identity": _text(manifest.get("replay_identity")) or _text(replay.get("source_replay_identity")),
            "campaign_execution_identity": _text(execution.get("campaign_execution_identity")),
            "diagnosis_identity": _text(diagnosis.get("diagnosis_identity")),
            "recalibration_identity": _text(recalibration.get("recalibration_identity")),
            "same_input_replay_identity": _text(replay.get("replay_assessment_identity")),
            "repeated_independent_oos_identity": _text(independent.get("independent_oos_identity")),
        },
        "synthesis_readiness_identity": "qrsr_" + _stable_digest(identity_seed)[:16],
        "final_readiness_outcome": final_outcome,
        "exact_next_permitted_action": exact_next_permitted_action,
        "summary": {
            "mandatory_gate_count": len(criteria),
            "failed_mandatory_gate_count": len(failed_mandatory),
            "passed_mandatory_gate_count": len(passed_mandatory),
            "failed_mandatory_gates": failed_mandatory,
            "passed_mandatory_gates": passed_mandatory,
            "supported_for_review_hypothesis_count": supported_for_review_count,
            "accepted_oos_count": int(diagnosis_counts.get("oos_accepted_count") or 0),
            "null_control_complete_count": int(diagnosis_counts.get("null_control_complete_count") or 0),
            "validation_completed_count": int(diagnosis_counts.get("validation_completed_count") or 0),
            "operator_summary": (
                "Synthesis remains blocked. Mandatory readiness gates fail on evidence density maturity, "
                "reason-record completeness, suppression usefulness, identity readiness, campaign and "
                "hypothesis lineage completeness, reproducibility, freshness, accepted OOS, repeated "
                "independent OOS, null controls, validation completeness, and operator-trusted decision "
                "reporting. trend_pullback_v1 is rejected; the remaining six theses are blocked before "
                "campaign lineage. Recalibration was not performed because no single criterion class was "
                "justified, and independent OOS could not be produced because no unseen valid path was "
                "materialized."
            ),
            "recommended_next_program_name": "qre_evidence_readiness_remediation_program",
        },
        "readiness_matrix": criteria,
        "blocking_gate_summary": [
            {
                "gate": row["criterion_id"],
                "blocking_reason": row["blocking_reason"],
                "remediation_class": row["remediation_class"],
            }
            for row in criteria
            if not row["satisfied"]
        ],
        "thesis_rows": thesis_rows,
        "remediation_backlog": remediation_backlog,
        "next_program_recommendation": {
            "program_name": "qre_evidence_readiness_remediation_program",
            "authorized_to_enqueue": False,
            "ordered_priorities": remediation_backlog,
            "synthesis_design_position": "last_and_blocked_until_all_mandatory_gates_pass",
        },
    }


def _atomic_write(path: Path, content: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    os.replace(temp_name, path)


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    _atomic_write(ARTIFACT_MARKDOWN, _render_markdown(snapshot))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize the ADE-QRE-017AD synthesis-readiness review.")
    parser.add_argument("--write", action="store_true", help="Persist JSON and Markdown outputs.")
    args = parser.parse_args(argv)

    snapshot = collect_snapshot()
    if args.write:
        write_outputs(snapshot)
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
