"""Screening failure attribution sidecar.

This module explains why candidate screening produced no survivors or
otherwise rejected candidates. It reads existing research sidecars only
and writes only screening-failure attribution reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

SCREENING_FAILURE_ATTRIBUTION_SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_REPORT_JSON_PATH: Final[Path] = Path(
    "research/screening_failure_attribution_latest.v1.json"
)
DEFAULT_REPORT_MD_PATH: Final[Path] = Path(
    "research/screening_failure_attribution_latest.md"
)

ARTIFACT_PATHS: Final[dict[str, Path]] = {
    "screening_evidence": Path("research/screening_evidence_latest.v1.json"),
    "run_filter_summary": Path("research/run_filter_summary_latest.v1.json"),
    "run_screening_candidates": Path(
        "research/run_screening_candidates_latest.v1.json"
    ),
    "empty_run_diagnostics": Path("research/empty_run_diagnostics_latest.v1.json"),
    "run_campaign": Path("research/run_campaign_latest.v1.json"),
    "controlled_eval": Path("research/controlled_eval_latest.v1.json"),
    "campaign_registry": Path("research/campaign_registry_latest.v1.json"),
    "campaign_evidence_ledger": Path("research/campaign_evidence_ledger_latest.v1.jsonl"),
    "research_state": Path("research/research_state_latest.v1.json"),
    "policy_filter_diagnostics": Path(
        "research/policy_filter_diagnostics_latest.v1.json"
    ),
}

CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "insufficient_trades",
    "no_oos_returns",
    "timeout",
    "cost_sensitivity",
    "parameter_instability",
    "data_coverage_gap",
    "strict_gate_rejection",
    "missing_diagnostics",
    "unknown_screening_failure",
)

REASON_TO_CLASSIFICATION: Final[dict[str, str]] = {
    "insufficient_trades": "insufficient_trades",
    "no_oos_samples": "no_oos_returns",
    "no_oos_returns": "no_oos_returns",
    "no_oos_daily_returns": "no_oos_returns",
    "candidate_budget_exceeded": "timeout",
    "screening_candidate_timeout": "timeout",
    "launcher_timeout": "timeout",
    "timeout": "timeout",
    "timed_out": "timeout",
    "cost_sensitive": "cost_sensitivity",
    "cost_sensitivity": "cost_sensitivity",
    "cost_sensitivity_flag": "cost_sensitivity",
    "unstable_parameter_neighborhood": "parameter_instability",
    "parameter_instability": "parameter_instability",
    "parameter_coverage_gap": "parameter_instability",
    "data_unavailable": "data_coverage_gap",
    "empty_dataset": "data_coverage_gap",
    "coverage_warning": "data_coverage_gap",
    "coverage_gap": "data_coverage_gap",
    "screening_criteria_not_met": "strict_gate_rejection",
    "strict_gate_rejection": "strict_gate_rejection",
    "expectancy_not_positive": "strict_gate_rejection",
    "profit_factor_below_floor": "strict_gate_rejection",
    "drawdown_above_exploratory_limit": "strict_gate_rejection",
}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso_utc(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
            for line in handle:
                line = line.strip()
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
    return events, "malformed" if malformed and not events else "present"


def load_current_artifacts(
    *,
    root: Path = Path("."),
    artifact_paths: dict[str, Path] = ARTIFACT_PATHS,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    payloads: dict[str, Any] = {}
    statuses: dict[str, dict[str, str]] = {}
    for name, relative_path in artifact_paths.items():
        path = root / relative_path
        if name == "campaign_evidence_ledger":
            payload, status = _read_jsonl(path)
        else:
            payload, status = _read_json(path)
        payloads[name] = payload
        statuses[name] = {"path": relative_path.as_posix(), "status": status}
    return payloads, statuses


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _observe(
    observations: list[dict[str, Any]],
    *,
    source: str,
    raw_reason: str,
    classification: str | None = None,
    subject: dict[str, Any] | None = None,
) -> None:
    classification = classification or REASON_TO_CLASSIFICATION.get(raw_reason)
    if classification is None:
        classification = "unknown_screening_failure"
    observations.append(
        {
            "source": source,
            "raw_reason": raw_reason,
            "classification": classification,
            "subject": subject or {},
        }
    )


def _screening_evidence_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    candidates = _list_value(payload.get("candidates"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        subject = {
            "candidate_id": candidate.get("candidate_id"),
            "strategy_name": candidate.get("strategy_name"),
            "asset": candidate.get("asset"),
            "interval": candidate.get("interval"),
            "stage_result": candidate.get("stage_result"),
        }
        for reason in _list_value(candidate.get("failure_reasons")):
            _observe(
                observations,
                source="screening_evidence.candidates.failure_reasons",
                raw_reason=str(reason),
                subject=subject,
            )
        sampling = _dict_value(candidate.get("sampling"))
        if sampling.get("coverage_warning"):
            _observe(
                observations,
                source="screening_evidence.candidates.sampling",
                raw_reason="coverage_warning",
                subject=subject,
            )
        if candidate.get("stage_result") == "unknown" and not _list_value(
            candidate.get("failure_reasons")
        ):
            _observe(
                observations,
                source="screening_evidence.candidates.stage_result",
                raw_reason="unknown_stage_result",
                classification="unknown_screening_failure",
                subject=subject,
            )
    summary = _dict_value(payload.get("summary"))
    for reason in _list_value(summary.get("dominant_failure_reasons")):
        _observe(
            observations,
            source="screening_evidence.summary.dominant_failure_reasons",
            raw_reason=str(reason),
        )
    return observations


def _filter_summary_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    reasons = _dict_value(payload.get("screening_rejection_reasons"))
    for reason, count in reasons.items():
        for _ in range(max(1, _safe_int(count, 1))):
            _observe(
                observations,
                source="run_filter_summary.screening_rejection_reasons",
                raw_reason=str(reason),
            )
    summary = _dict_value(payload.get("summary"))
    nested = _dict_value(summary.get("screening_rejection_reasons"))
    for reason, count in nested.items():
        for _ in range(max(1, _safe_int(count, 1))):
            _observe(
                observations,
                source="run_filter_summary.summary.screening_rejection_reasons",
                raw_reason=str(reason),
            )
    return observations


def _run_screening_candidate_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for candidate in _list_value(payload.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        reason = candidate.get("reason_code")
        if not reason and candidate.get("final_status") == "timed_out":
            reason = "timed_out"
        if not reason:
            continue
        _observe(
            observations,
            source="run_screening_candidates.candidates.reason_code",
            raw_reason=str(reason),
            subject={
                "candidate_id": candidate.get("candidate_id"),
                "strategy": candidate.get("strategy"),
                "final_status": candidate.get("final_status"),
            },
        )
    return observations


def _empty_run_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    summary = _dict_value(payload.get("summary"))
    for reason in _list_value(summary.get("primary_drop_reasons")):
        _observe(
            observations,
            source="empty_run_diagnostics.summary.primary_drop_reasons",
            raw_reason=str(reason),
        )
    if _safe_int(summary.get("evaluations_with_oos_daily_returns")) == 0 and _safe_int(
        summary.get("evaluations_count")
    ) > 0:
        _observe(
            observations,
            source="empty_run_diagnostics.summary.evaluations_with_oos_daily_returns",
            raw_reason="no_oos_daily_returns",
        )
    for pair in _list_value(payload.get("pairs")):
        if not isinstance(pair, dict):
            continue
        reason = pair.get("drop_reason")
        if reason:
            _observe(
                observations,
                source="empty_run_diagnostics.pairs.drop_reason",
                raw_reason=str(reason),
                subject={"asset": pair.get("asset"), "interval": pair.get("interval")},
            )
    return observations


def _run_campaign_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    latest = _dict_value(payload.get("summary"))
    rejection_reasons = _dict_value(latest.get("screening_rejection_reasons"))
    for reason, count in rejection_reasons.items():
        for _ in range(max(1, _safe_int(count, 1))):
            _observe(
                observations,
                source="run_campaign.summary.screening_rejection_reasons",
                raw_reason=str(reason),
            )
    for batch in _list_value(payload.get("batches")):
        if not isinstance(batch, dict):
            continue
        reason = batch.get("reason_code") or batch.get("error_type")
        if reason:
            _observe(
                observations,
                source="run_campaign.batches.reason",
                raw_reason=str(reason),
                subject={"batch_id": batch.get("batch_id"), "status": batch.get("status")},
            )
    return observations


def _campaign_outcome_observations(
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    registry = _dict_value(artifacts.get("campaign_registry"))
    for cid, record in _dict_value(registry.get("campaigns")).items():
        if not isinstance(record, dict):
            continue
        for key in ("reason_code", "dominant_failure_mode"):
            reason = record.get(key)
            if reason and reason != "none":
                _observe(
                    observations,
                    source=f"campaign_registry.campaigns.{key}",
                    raw_reason=str(reason),
                    subject={"campaign_id": record.get("campaign_id") or cid},
                )
        for reason in _list_value(record.get("failure_reasons")):
            _observe(
                observations,
                source="campaign_registry.campaigns.failure_reasons",
                raw_reason=str(reason),
                subject={"campaign_id": record.get("campaign_id") or cid},
            )
    for event in _list_value(artifacts.get("campaign_evidence_ledger")):
        if not isinstance(event, dict):
            continue
        reason = event.get("reason_code") or event.get("dominant_failure_mode")
        if reason and reason != "none":
            _observe(
                observations,
                source="campaign_evidence_ledger.reason",
                raw_reason=str(reason),
                subject={"campaign_id": event.get("campaign_id")},
            )

    research_state = _dict_value(artifacts.get("research_state"))
    failure = _dict_value(research_state.get("failure_attribution"))
    if (
        failure.get("state") == "screening_evaluability_unattributed"
        and artifact_status["screening_evidence"]["status"] != "present"
    ):
        _observe(
            observations,
            source="research_state.failure_attribution",
            raw_reason="missing_screening_drop_reasons",
            classification="missing_diagnostics",
        )
    return observations


def collect_observations(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    if isinstance(artifacts.get("screening_evidence"), dict):
        observations.extend(
            _screening_evidence_observations(artifacts["screening_evidence"])
        )
    if isinstance(artifacts.get("run_filter_summary"), dict):
        observations.extend(
            _filter_summary_observations(artifacts["run_filter_summary"])
        )
    if isinstance(artifacts.get("run_screening_candidates"), dict):
        observations.extend(
            _run_screening_candidate_observations(
                artifacts["run_screening_candidates"]
            )
        )
    if isinstance(artifacts.get("empty_run_diagnostics"), dict):
        observations.extend(_empty_run_observations(artifacts["empty_run_diagnostics"]))
    if isinstance(artifacts.get("run_campaign"), dict):
        observations.extend(_run_campaign_observations(artifacts["run_campaign"]))
    observations.extend(
        _campaign_outcome_observations(
            artifacts=artifacts,
            artifact_status=artifact_status,
        )
    )
    if not observations and all(
        artifact_status[name]["status"] != "present"
        for name in (
            "screening_evidence",
            "run_filter_summary",
            "run_screening_candidates",
            "empty_run_diagnostics",
        )
    ):
        _observe(
            observations,
            source="artifact_inventory",
            raw_reason="missing_screening_diagnostics",
            classification="missing_diagnostics",
        )
    if not observations:
        _observe(
            observations,
            source="artifact_inventory",
            raw_reason="no_screening_failure_reason_observed",
            classification="unknown_screening_failure",
        )
    return observations


def _classification_rows(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(item["classification"]) for item in observations)
    raw_by_class: dict[str, Counter[str]] = {name: Counter() for name in CLASSIFICATIONS}
    sources_by_class: dict[str, set[str]] = {name: set() for name in CLASSIFICATIONS}
    examples_by_class: dict[str, list[dict[str, Any]]] = {
        name: [] for name in CLASSIFICATIONS
    }
    for item in observations:
        classification = str(item["classification"])
        if classification not in raw_by_class:
            classification = "unknown_screening_failure"
        raw_by_class[classification][str(item["raw_reason"])] += 1
        sources_by_class[classification].add(str(item["source"]))
        if len(examples_by_class[classification]) < 5:
            examples_by_class[classification].append(item)
    rows = []
    for classification in CLASSIFICATIONS:
        rows.append(
            {
                "classification": classification,
                "status": "observed" if counts.get(classification, 0) > 0 else "not_observed",
                "count": int(counts.get(classification, 0)),
                "raw_reasons": dict(sorted(raw_by_class[classification].items())),
                "sources": sorted(sources_by_class[classification]),
                "examples": examples_by_class[classification],
            }
        )
    return rows


def _primary_classification(rows: list[dict[str, Any]]) -> str:
    observed = [row for row in rows if int(row["count"]) > 0]
    if not observed:
        return "unknown_screening_failure"
    priority = {name: index for index, name in enumerate(CLASSIFICATIONS)}
    observed.sort(
        key=lambda row: (
            -int(row["count"]),
            priority.get(str(row["classification"]), 999),
            str(row["classification"]),
        )
    )
    return str(observed[0]["classification"])


def build_screening_failure_attribution_payload(
    *,
    artifacts: dict[str, Any],
    artifact_status: dict[str, dict[str, str]],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _now_utc()
    observations = collect_observations(
        artifacts=artifacts,
        artifact_status=artifact_status,
    )
    rows = _classification_rows(observations)
    primary = _primary_classification(rows)
    counts = {
        row["classification"]: row["count"]
        for row in rows
        if int(row["count"]) > 0
    }
    return {
        "schema_version": SCREENING_FAILURE_ATTRIBUTION_SCHEMA_VERSION,
        "generated_at_utc": _iso_utc(generated),
        "source_screening_evidence_path": artifact_status["screening_evidence"]["path"],
        "artifact_inputs": artifact_status,
        "summary": {
            "primary_classification": primary,
            "classification_counts": counts,
            "observation_count": len(observations),
            "attributed": primary
            not in {"missing_diagnostics", "unknown_screening_failure"},
        },
        "classifications": rows,
        "observations": observations,
        "recommended_next_action": (
            "inspect_gate_diagnostics"
            if primary != "missing_diagnostics"
            else "inspect_screening_instrumentation"
        ),
        "safety_invariants": {
            "runs_research": False,
            "runs_campaign_launcher": False,
            "mutates_screening_behavior": False,
            "mutates_campaign_artifacts": False,
            "writes_only_screening_failure_attribution_sidecars": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "frozen_contracts_unchanged": True,
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Screening Failure Attribution",
        "",
        "## Summary",
        f"- Generated at UTC: `{payload.get('generated_at_utc')}`",
        f"- Source screening evidence: `{payload.get('source_screening_evidence_path')}`",
        f"- Primary classification: `{summary.get('primary_classification')}`",
        f"- Attributed: {summary.get('attributed')}",
        f"- Observation count: {summary.get('observation_count')}",
        f"- Classification counts: {json.dumps(summary.get('classification_counts') or {}, sort_keys=True)}",
        "",
        "## Classifications",
        *[
            f"- `{row['classification']}`: {row['status']} (count {row['count']})"
            for row in payload.get("classifications") or []
        ],
        "",
        "## Evidence Sources",
        *[
            f"- `{source}`"
            for source in sorted(
                {
                    str(obs.get("source"))
                    for obs in payload.get("observations") or []
                }
            )
        ],
        "",
        "## What To Expect Next",
        (
            "- Use the primary classification to choose between gate diagnostics, "
            "instrumentation repair, or an operator-gated research change."
        ),
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
    payload = build_screening_failure_attribution_payload(
        artifacts=artifacts,
        artifact_status=statuses,
        generated_at_utc=generated_at_utc,
    )
    write_sidecar_atomic(root / report_json, payload)
    _write_text_atomic(root / report_md, render_markdown_report(payload))
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.screening_failure_attribution",
        description="Classify screening drop reasons from existing artifacts.",
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        help="Read current QRE sidecars and write screening failure attribution.",
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON_PATH)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD_PATH)
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
    print(
        "screening_failure_attribution: "
        f"primary={payload['summary']['primary_classification']} "
        f"observations={payload['summary']['observation_count']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ARTIFACT_PATHS",
    "CLASSIFICATIONS",
    "DEFAULT_REPORT_JSON_PATH",
    "DEFAULT_REPORT_MD_PATH",
    "SCREENING_FAILURE_ATTRIBUTION_SCHEMA_VERSION",
    "build_from_current_artifacts",
    "build_screening_failure_attribution_payload",
    "collect_observations",
    "load_current_artifacts",
    "main",
    "render_markdown_report",
]
