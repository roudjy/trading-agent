"""Deterministic no-authority retrieval coverage over trusted-loop memory."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_research import research_memory

SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "ade-qre-014j-2026-05-25"
REPORT_KIND: Final[str] = "qre_research_memory_retrieval_coverage"

DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_retrieval_coverage")
LATEST_NAME: Final[str] = "latest.json"
HISTORY_NAME: Final[str] = "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/qre_research_retrieval_coverage/"

DEFAULT_ARTIFACT_PATHS: Final[tuple[Path, ...]] = (
    Path("docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md"),
    Path("logs/reason_records/manifest.v1.json"),
    Path("logs/reason_record_evidence_density/latest.json"),
    Path("logs/failure_action_mapping_minimal/latest.json"),
    Path("logs/qre_research_diagnostics_loop/latest.json"),
    Path("logs/research_observability_minimal/latest.json"),
    Path("logs/trusted_loop_materialization/latest.json"),
    Path("logs/intelligent_routing_minimal/latest.json"),
    Path("logs/sampling_intelligence_minimal/latest.json"),
    Path("logs/qre_candidate_quality_framework/latest.json"),
    Path("logs/qre_multibasket_portfolio_intelligence/latest.json"),
)

_COVERAGE_SPECS: Final[tuple[dict[str, Any], ...]] = (
    {
        "coverage_id": "trusted_loop_reasons",
        "label": "prior trusted-loop reasons",
        "query": "reason reason_codes reason_text evidence_refs trusted loop",
        "required_link_signals": (
            "evidence_refs",
            "reason_codes",
            "record_id",
            "subject_id",
            "source_ref",
        ),
        "operator_need": "find why a prior routing, sampling, scoring, or blocker decision existed",
    },
    {
        "coverage_id": "trusted_loop_failures",
        "label": "prior trusted-loop failures",
        "query": "failure failed classification raw_reasons failure_action_mapping",
        "required_link_signals": (
            "action_hint",
            "classification",
            "failure_action",
            "raw_reasons",
            "total_failures",
        ),
        "operator_need": "find earlier failure context before repeating similar research",
    },
    {
        "coverage_id": "trusted_loop_blockers",
        "label": "prior trusted-loop blockers",
        "query": "blocker blocked block_reasons missing_evidence fail_closed",
        "required_link_signals": (
            "block_reasons",
            "blocking_reasons",
            "fail_closed",
            "missing_evidence",
            "synthesis_blocker",
        ),
        "operator_need": "find active or historical blockers and the evidence they lack",
    },
    {
        "coverage_id": "trusted_loop_actions",
        "label": "prior trusted-loop actions",
        "query": "action policy_action recommended_next_action recommended_operator_step action_hint",
        "required_link_signals": (
            "action_hint",
            "actionable",
            "operator_explanation",
            "policy_action",
            "recommended_next_action",
            "recommended_operator_step",
        ),
        "operator_need": "find the prior next-action or stop-action attached to evidence",
    },
)


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _match_link_signals(
    match: Mapping[str, Any],
    *,
    required_link_signals: Sequence[str],
) -> list[str]:
    haystack = " ".join(
        str(match.get(key) or "")
        for key in (
            "artifact_id",
            "artifact_path",
            "record_kind",
            "title",
            "text_preview",
        )
    ).lower()
    return sorted({signal for signal in required_link_signals if signal in haystack})


def _coverage_row(
    *,
    memory: Mapping[str, Any],
    spec: Mapping[str, Any],
    limit: int,
) -> dict[str, Any]:
    matches = research_memory.retrieve(memory, str(spec["query"]), limit=limit)
    required = tuple(str(signal) for signal in spec["required_link_signals"])
    annotated_matches: list[dict[str, Any]] = []
    linked_count = 0
    for match in matches:
        signals = _match_link_signals(match, required_link_signals=required)
        linked = bool(signals)
        linked_count += int(linked)
        annotated_matches.append(
            {
                "artifact_id": match["artifact_id"],
                "artifact_path": match["artifact_path"],
                "record_kind": match["record_kind"],
                "title": match["title"],
                "score": match["score"],
                "ontology_tags": match["ontology_tags"],
                "link_signals": signals,
                "linked_enough_for_calibration_context": linked,
                "text_preview": match["text_preview"],
            }
        )

    if not matches:
        status = "missing_retrieval"
        missing_links = ["no_retrieval_matches"]
    elif linked_count == 0:
        status = "missing_link"
        missing_links = [f"no_required_link_signals:{','.join(required)}"]
    else:
        status = "covered"
        missing_links = []

    return {
        "coverage_id": spec["coverage_id"],
        "label": spec["label"],
        "status": status,
        "query": spec["query"],
        "operator_need": spec["operator_need"],
        "required_link_signals": list(required),
        "retrieved_match_count": len(matches),
        "linked_match_count": linked_count,
        "missing_retrieval_links": missing_links,
        "matches": annotated_matches,
        "retrieval_role": "context_only_not_authority",
    }


def _operator_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    can_retrieve = [str(row["label"]) for row in rows if row.get("status") == "covered"]
    cannot_retrieve = [
        {
            "label": row["label"],
            "status": row["status"],
            "missing_retrieval_links": row["missing_retrieval_links"],
        }
        for row in rows
        if row.get("status") != "covered"
    ]
    if not cannot_retrieve:
        text = (
            "Trusted-loop reasons, failures, blockers, and actions are retrievable "
            "as context with explicit local links. Retrieval remains non-authoritative."
        )
    else:
        text = (
            "Some trusted-loop retrieval surfaces are missing matches or link "
            "signals; inspect missing_retrieval_links before using retrieval for "
            "routing or sampling calibration context."
        )
    return {
        "can_retrieve": can_retrieve,
        "cannot_retrieve": cannot_retrieve,
        "summary": text,
    }


def build_retrieval_coverage(
    *,
    artifact_paths: Iterable[Path] | None = None,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    ts = generated_at_utc or _utcnow()
    memory = research_memory.build_research_memory(
        artifact_paths=artifact_paths or DEFAULT_ARTIFACT_PATHS,
        repo_root=repo_root,
        generated_at_utc=ts,
    )
    rows = [
        _coverage_row(memory=memory, spec=spec, limit=limit)
        for spec in _COVERAGE_SPECS
    ]
    covered_count = sum(1 for row in rows if row["status"] == "covered")
    missing_count = len(rows) - covered_count
    summary = {
        "status": "ready" if missing_count == 0 else "not_ready",
        "retrieval_coverage_ready": missing_count == 0,
        "required_surface_count": len(rows),
        "covered_surface_count": covered_count,
        "missing_or_unlinked_surface_count": missing_count,
        "coverage_score": round(covered_count / len(rows), 6) if rows else 0.0,
        "memory_entry_count": memory["summary"]["entry_count"],
        "missing_artifact_count": memory["summary"]["missing_artifact_count"],
        "missing_artifacts": memory["missing_artifacts"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "summary": summary,
        "addendum_reference": {
            "source": "Roadmap v6 Addendum 2",
            "usage": "reference_taxonomy_only",
            "runtime_activation": False,
        },
        "coverage": rows,
        "operator_summary": _operator_summary(rows),
        "memory_summary": memory["summary"],
        "artifact_paths": memory["artifact_paths"],
        "missing_artifacts": memory["missing_artifacts"],
        "authority_boundary": {
            "retrieval_is_context_not_authority": True,
            "can_inform_later_calibration_review": True,
            "can_route_or_sample": False,
            "can_mutate_campaigns": False,
            "can_approve_or_synthesize_strategies": False,
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_vector_database": False,
            "uses_embeddings": False,
            "uses_hidden_ml": False,
            "uses_llm_authority": False,
            "uses_network": False,
            "uses_subprocess": False,
            "activates_addendum_runtime": False,
            "mutates_campaigns": False,
            "mutates_routing": False,
            "mutates_research_outputs": False,
            "enables_strategy_synthesis": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError(f"retrieval_coverage: refusing write outside allowlist: {path!r}")


def write_retrieval_coverage_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(snapshot["generated_at_utc"]).replace(":", "-")
    latest = base / LATEST_NAME
    timestamped = base / f"{timestamp}.json"
    history = base / HISTORY_NAME
    payload = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_timestamped = timestamped.with_suffix(timestamped.suffix + ".tmp")
    tmp_timestamped.write_text(payload, encoding="utf-8")
    os.replace(tmp_timestamped, timestamped)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest, root=repo_root),
        "timestamped": _rel(timestamped, root=repo_root),
        "history": _rel(history, root=repo_root),
    }


def read_retrieval_coverage_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_retrieval_coverage",
            "retrieval_coverage_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_retrieval_coverage",
            "retrieval_coverage_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, dict) else None
    ready = bool(summary.get("retrieval_coverage_ready")) if isinstance(summary, dict) else False
    return {
        "status": "ready" if ready else "not_ready",
        "retrieval_coverage_ready": ready,
        "path": _rel(latest, root=repo_root),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="packages.qre_research.retrieval_coverage",
        description="Measure deterministic no-authority trusted-loop retrieval coverage.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_retrieval_coverage_status(), sort_keys=True, indent=2))
        return 0

    snapshot = build_retrieval_coverage(generated_at_utc=args.frozen_utc)
    if not args.no_write:
        snapshot["_artifact_paths"] = write_retrieval_coverage_outputs(snapshot)
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_ARTIFACT_PATHS",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_retrieval_coverage",
    "read_retrieval_coverage_status",
    "write_retrieval_coverage_outputs",
]
