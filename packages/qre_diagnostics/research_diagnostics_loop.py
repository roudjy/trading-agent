"""Read-only QRE research diagnostics loop digest.

This module aggregates existing sidecar evidence into an operator-facing
failure -> evidence -> next diagnostic view. It never invokes upstream
producers and never mutates campaigns, routing, strategies, or execution paths.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_research_diagnostics_loop"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_diagnostics_loop")
LATEST_NAME: Final[str] = "latest.json"
HISTORY_NAME: Final[str] = "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/qre_research_diagnostics_loop/"

SCREENING_ATTRIBUTION_PATH: Final[Path] = Path(
    "research/screening_failure_attribution_latest.v1.json"
)
FAILURE_ACTION_MAPPING_PATH: Final[Path] = Path("logs/failure_action_mapping_minimal/latest.json")
DATA_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")
RESEARCH_MEMORY_PATH: Final[Path] = Path("logs/qre_research_memory/latest.json")

SOURCE_PATHS: Final[Mapping[str, Path]] = {
    "screening_failure_attribution": SCREENING_ATTRIBUTION_PATH,
    "failure_action_mapping": FAILURE_ACTION_MAPPING_PATH,
    "data_manifest": DATA_MANIFEST_PATH,
    "source_quality": SOURCE_QUALITY_PATH,
    "research_memory": RESEARCH_MEMORY_PATH,
}

STOP_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "hold_no_action",
        "hold_no_action_until_evidence_improves",
        "preserve_negative_result",
        "preserve_negative_result_for_unstable_parameter_region",
    }
)

DIAGNOSTIC_BY_ACTION_KEYWORD: Final[tuple[tuple[str, str], ...]] = (
    ("identity", "inspect_source_identity_readiness"),
    ("pipeline", "inspect_data_pipeline_readiness"),
    ("coverage", "inspect_data_foundation_readiness"),
    ("data", "inspect_data_foundation_readiness"),
    ("metric", "inspect_screening_metric_instrumentation"),
    ("instrumentation", "inspect_screening_instrumentation"),
    ("policy", "inspect_policy_trace_evidence"),
    ("synthesis", "inspect_synthesis_gate_evidence"),
    ("oos", "inspect_oos_sample_window"),
    ("sample", "inspect_oos_sample_window"),
    ("timeframe", "inspect_oos_sample_window"),
    ("volatility", "inspect_regime_or_volatility_evidence"),
    ("regime", "inspect_regime_or_volatility_evidence"),
    ("cost", "inspect_cost_assumption_evidence"),
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path, *, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json_source(source_id: str, path: Path, *, repo_root: Path) -> dict[str, Any]:
    full_path = repo_root / path
    if not full_path.is_file():
        return {
            "source_id": source_id,
            "available": False,
            "status": "missing",
            "path": _rel(full_path, repo_root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(full_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "source_id": source_id,
            "available": False,
            "status": "invalid",
            "path": _rel(full_path, repo_root=repo_root),
            "fails_closed": True,
        }
    if not isinstance(payload, dict):
        return {
            "source_id": source_id,
            "available": False,
            "status": "invalid",
            "path": _rel(full_path, repo_root=repo_root),
            "fails_closed": True,
        }
    return {
        "source_id": source_id,
        "available": True,
        "status": _source_status(source_id, payload),
        "path": _rel(full_path, repo_root=repo_root),
        "fails_closed": _source_fails_closed(source_id, payload),
        "schema_version": payload.get("schema_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "payload": payload,
    }


def _source_status(source_id: str, payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        return "present"
    if source_id == "screening_failure_attribution":
        count = _safe_int(summary.get("observation_count"))
        return "ready" if count > 0 else "not_ready"
    if source_id in {"data_manifest", "source_quality"}:
        return "ready" if bool(summary.get("research_ready")) else "not_ready"
    if source_id == "research_memory":
        return "ready" if bool(summary.get("research_memory_ready")) else "not_ready"
    if source_id == "failure_action_mapping":
        counts = payload.get("counts")
        total = counts.get("total") if isinstance(counts, Mapping) else None
        return "ready" if _safe_int(total) > 0 else "not_ready"
    return "present"


def _source_fails_closed(source_id: str, payload: Mapping[str, Any]) -> bool:
    if source_id == "screening_failure_attribution":
        summary = payload.get("summary")
        return not (isinstance(summary, Mapping) and _safe_int(summary.get("observation_count")) > 0)
    if source_id in {"data_manifest", "source_quality"}:
        summary = payload.get("summary")
        return not (isinstance(summary, Mapping) and bool(summary.get("research_ready")))
    if source_id == "research_memory":
        summary = payload.get("summary")
        return not (isinstance(summary, Mapping) and bool(summary.get("research_memory_ready")))
    return False


def _safe_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _action_to_next_diagnostic(action: str) -> str:
    normalized = action.lower()
    if normalized in STOP_ACTIONS:
        return "stop_until_evidence_improves"
    for keyword, diagnostic in DIAGNOSTIC_BY_ACTION_KEYWORD:
        if keyword in normalized:
            return diagnostic
    return "inspect_screening_failure_evidence"


def _operator_explanation(
    *,
    classification: str,
    evidence_count: int,
    source_count: int,
    action: str,
    next_diagnostic: str,
) -> str:
    if next_diagnostic.startswith("stop_"):
        return (
            f"{classification} has {evidence_count} evidence records across {source_count} "
            f"sources; action {action} is a stop/hold recommendation, not a reroute."
        )
    return (
        f"{classification} has {evidence_count} evidence records across {source_count} "
        f"sources; next diagnostic is {next_diagnostic}."
    )


def _failure_action_items(source: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    items = payload.get("items")
    if not isinstance(items, Sequence) or isinstance(items, str | bytes):
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        subject_id = item.get("subject_id")
        if isinstance(subject_id, str) and subject_id:
            out[subject_id] = item
    return out


def _research_memory_context(source: Mapping[str, Any], classification: str) -> dict[str, Any]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return {"available": False, "match_count": 0, "matches": []}
    matches: list[Mapping[str, Any]] = []
    related = payload.get("related_failures")
    if isinstance(related, Mapping):
        for row in _mapping_sequence(related.get("matches")):
            text = json.dumps(row, sort_keys=True)
            if classification in text:
                matches.append(row)
    if not matches:
        for row in _mapping_sequence(payload.get("entries")):
            text = json.dumps(row, sort_keys=True)
            if classification in text:
                matches.append(row)
            if len(matches) >= 3:
                break
    return {
        "available": bool(source.get("available")),
        "match_count": len(matches),
        "matches": [_bounded_memory_match(row) for row in matches[:3]],
    }


def _bounded_memory_match(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": row.get("artifact_id"),
        "record_kind": row.get("record_kind"),
        "ontology_tags": row.get("ontology_tags", []),
        "content_hash": row.get("content_hash"),
    }


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _screening_rows(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    payload = source.get("payload")
    if not isinstance(payload, Mapping):
        return []
    return [
        row
        for row in _mapping_sequence(payload.get("classifications"))
        if _safe_int(row.get("count")) > 0
    ]


def _build_diagnostic_chain(sources: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    screening = sources["screening_failure_attribution"]
    failure_actions = _failure_action_items(sources["failure_action_mapping"])
    memory = sources["research_memory"]
    rows: list[dict[str, Any]] = []
    for rank, row in enumerate(_screening_rows(screening)):
        classification = str(row.get("classification") or "unknown_screening_failure")
        action_hint = row.get("action_hint") if isinstance(row.get("action_hint"), Mapping) else {}
        action = str(action_hint.get("action") or "hold_no_action_until_evidence_improves")
        subject_id = f"screening:{classification}"
        failure_action = failure_actions.get(subject_id, {})
        failure_code = str(failure_action.get("failure_code") or "not_mapped")
        mapped_action = str(failure_action.get("recommended_action") or action)
        next_diagnostic = _action_to_next_diagnostic(mapped_action)
        source_count = len(row.get("sources") or [])
        evidence_count = _safe_int(row.get("count"))
        rows.append(
            {
                "rank": rank,
                "subject_id": subject_id,
                "failure_classification": classification,
                "failure_code": failure_code,
                "evidence_count": evidence_count,
                "evidence_sources": sorted(str(item) for item in row.get("sources") or []),
                "raw_reasons": dict(sorted(dict(row.get("raw_reasons") or {}).items())),
                "screening_action_hint": {
                    "action": action,
                    "reason": action_hint.get("reason"),
                    "read_only": bool(action_hint.get("read_only", True)),
                    "mutates_routing": bool(action_hint.get("mutates_routing", False)),
                    "mutates_strategy": bool(action_hint.get("mutates_strategy", False)),
                },
                "failure_action_mapping": _bounded_failure_action(failure_action),
                "research_memory_context": _research_memory_context(memory, classification),
                "next_diagnostic": next_diagnostic,
                "operator_explanation": _operator_explanation(
                    classification=classification,
                    evidence_count=evidence_count,
                    source_count=source_count,
                    action=mapped_action,
                    next_diagnostic=next_diagnostic,
                ),
                "safety": {
                    "read_only": True,
                    "mutates_campaign_queue": False,
                    "mutates_routing": False,
                    "mutates_strategy": False,
                    "safe_to_execute": False,
                },
            }
        )
    rows.sort(
        key=lambda item: (
            item["rank"],
            item["failure_classification"],
            item["subject_id"],
        )
    )
    for rank, item in enumerate(rows):
        item["rank"] = rank
    return rows


def _bounded_failure_action(row: Mapping[str, Any]) -> dict[str, Any]:
    reason = row.get("reason_record") if isinstance(row.get("reason_record"), Mapping) else {}
    return {
        "available": bool(row),
        "failure_code": row.get("failure_code"),
        "recommended_action": row.get("recommended_action"),
        "severity": row.get("severity"),
        "reason_codes": list(reason.get("reason_codes") or []),
        "reason_text": reason.get("reason_text"),
    }


def _summarize_sources(sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for source_id, source in sorted(sources.items()):
        summary[source_id] = {
            key: source.get(key)
            for key in (
                "source_id",
                "available",
                "status",
                "path",
                "fails_closed",
                "schema_version",
                "generated_at_utc",
            )
            if key in source
        }
    return summary


def build_diagnostics_loop_digest(
    *,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    source_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    source_map = source_paths or SOURCE_PATHS
    generated = generated_at_utc or _utcnow()
    sources = {
        source_id: _read_json_source(source_id, path, repo_root=repo_root)
        for source_id, path in sorted(source_map.items())
    }
    chain = _build_diagnostic_chain(sources)
    missing_sources = [
        source_id
        for source_id, source in sorted(sources.items())
        if source.get("status") == "missing"
    ]
    invalid_sources = [
        source_id
        for source_id, source in sorted(sources.items())
        if source.get("status") == "invalid"
    ]
    blocking_reasons = []
    if not chain:
        blocking_reasons.append("missing_failure_diagnostic_chain")
    if invalid_sources:
        blocking_reasons.append("invalid_upstream_source")
    recommended = "inspect_next_diagnostic"
    if not chain:
        recommended = "stop_collect_upstream_sidecars"
    elif all(row["next_diagnostic"].startswith("stop_") for row in chain):
        recommended = "stop_until_evidence_improves"
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "mode": "dry-run",
        "safe_to_execute": False,
        "summary": {
            "status": "ready" if chain and not invalid_sources else "not_ready",
            "fail_closed": not bool(chain) or bool(invalid_sources),
            "source_count": len(sources),
            "available_source_count": sum(
                1 for source in sources.values() if bool(source.get("available"))
            ),
            "missing_source_count": len(missing_sources),
            "invalid_source_count": len(invalid_sources),
            "diagnostic_count": len(chain),
            "primary_failure_classification": (
                chain[0]["failure_classification"] if chain else None
            ),
            "recommended_operator_step": recommended,
            "blocking_reasons": blocking_reasons,
            "missing_sources": missing_sources,
            "invalid_sources": invalid_sources,
        },
        "sources": _summarize_sources(sources),
        "diagnostic_chain": chain,
        "operator_explanations": [row["operator_explanation"] for row in chain],
        "safety_invariants": {
            "read_only": True,
            "uses_existing_sidecars_only": True,
            "invokes_upstream_producers": False,
            "mutates_campaign_queue": False,
            "mutates_routing": False,
            "mutates_strategy_or_presets": False,
            "dashboard_mutation_routes": False,
            "adaptive_learning_side_effects": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError(f"qre_research_diagnostics_loop: refusing write outside allowlist: {path!r}")


def write_diagnostics_loop_outputs(
    digest: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(digest["generated_at_utc"]).replace(":", "-")
    latest = base / LATEST_NAME
    timestamped = base / f"{timestamp}.json"
    history = base / HISTORY_NAME
    payload = json.dumps(digest, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_timestamped = timestamped.with_suffix(timestamped.suffix + ".tmp")
    tmp_timestamped.write_text(payload, encoding="utf-8")
    os.replace(tmp_timestamped, timestamped)

    compact = json.dumps(digest, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest, repo_root=repo_root),
        "timestamped": _rel(timestamped, repo_root=repo_root),
        "history": _rel(history, repo_root=repo_root),
    }


def read_diagnostics_loop_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_research_diagnostics_loop",
            "diagnostics_loop_ready": False,
            "path": _rel(latest, repo_root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_research_diagnostics_loop",
            "diagnostics_loop_ready": False,
            "path": _rel(latest, repo_root=repo_root),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    ready = bool(isinstance(summary, Mapping) and summary.get("status") == "ready")
    return {
        "status": "ready" if ready else "not_ready",
        "diagnostics_loop_ready": ready,
        "path": _rel(latest, repo_root=repo_root),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="packages.qre_diagnostics.research_diagnostics_loop",
        description="Build a read-only QRE research diagnostics-loop digest.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_diagnostics_loop_status(), sort_keys=True, indent=2))
        return 0

    digest = build_diagnostics_loop_digest(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        digest["_artifact_paths"] = write_diagnostics_loop_outputs(digest)
    print(json.dumps(digest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_diagnostics_loop_digest",
    "read_diagnostics_loop_status",
    "write_diagnostics_loop_outputs",
]
