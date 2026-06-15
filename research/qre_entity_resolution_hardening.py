from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_research_memory_coverage as memory_coverage


REPORT_KIND: Final[str] = "qre_entity_resolution_hardening"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_entity_resolution_hardening")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_entity_resolution_hardening/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _distinct(values: Sequence[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value)})


def _normalise_entity(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": str(observation.get("artifact_id") or ""),
        "subject_id": str(observation.get("subject_id") or ""),
        "record_kind": str(observation.get("record_kind") or ""),
        "entity_id": str(observation.get("entity_id") or ""),
        "entity_type": str(observation.get("entity_type") or "unknown"),
        "label": str(observation.get("label") or ""),
        "confidence": str(observation.get("confidence") or "unknown"),
        "ambiguity_status": str(observation.get("ambiguity_status") or "unknown"),
        "evidence": list(observation.get("evidence") or []),
    }


def build_entity_resolution_hardening(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    memory = memory_coverage.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    memory_summary = memory.get("summary") if isinstance(memory.get("summary"), Mapping) else {}
    entries = memory.get("entries") if isinstance(memory.get("entries"), list) else []

    observations: list[dict[str, Any]] = []
    by_entity_id: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_artifact_id: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        resolved_entities = entry.get("resolved_entities")
        if not isinstance(resolved_entities, list):
            continue
        for resolved in resolved_entities:
            if not isinstance(resolved, Mapping):
                continue
            observation = _normalise_entity(
                {
                    **resolved,
                    "artifact_id": entry.get("artifact_id"),
                    "subject_id": entry.get("subject_id"),
                    "record_kind": entry.get("record_kind"),
                }
            )
            observations.append(observation)
            by_entity_id[observation["entity_id"]].append(observation)
            by_artifact_id[observation["artifact_id"]].append(observation)

    canonical_entities: list[dict[str, Any]] = []
    blocked_entities: list[dict[str, Any]] = []
    artifact_summaries: list[dict[str, Any]] = []

    for entity_id in sorted(by_entity_id):
        entity_rows = by_entity_id[entity_id]
        labels = _distinct([row["label"] for row in entity_rows])
        entity_types = _distinct([row["entity_type"] for row in entity_rows])
        artifact_ids = _distinct([row["artifact_id"] for row in entity_rows])
        ambiguity_statuses = _distinct([row["ambiguity_status"] for row in entity_rows])

        blocking_reasons: list[str] = []
        if len(entity_types) > 1:
            blocking_reasons.append("cross_artifact_entity_type_conflict")
        if len(labels) > 1:
            blocking_reasons.append("cross_artifact_label_conflict")
        if any(status != "resolved" for status in ambiguity_statuses):
            blocking_reasons.append("unresolved_observation_visible")

        canonical_entities.append(
            {
                "entity_id": entity_id,
                "canonical_label": labels[0] if len(labels) == 1 else "",
                "canonical_entity_type": entity_types[0] if len(entity_types) == 1 else "ambiguous",
                "source_artifact_ids": artifact_ids,
                "observation_count": len(entity_rows),
                "distinct_labels": labels,
                "distinct_entity_types": entity_types,
                "resolved_observation_count": sum(
                    1 for row in entity_rows if row["ambiguity_status"] == "resolved"
                ),
                "ambiguity_blocked": bool(blocking_reasons),
                "blocking_reasons": blocking_reasons,
            }
        )
        if blocking_reasons:
            blocked_entities.append(
                {
                    "entity_id": entity_id,
                    "subject_ids": _distinct([row["subject_id"] for row in entity_rows]),
                    "artifact_ids": artifact_ids,
                    "reason": "cross_artifact_ambiguity_visible",
                    "blocking_reasons": blocking_reasons,
                }
            )

    for artifact_id in sorted(by_artifact_id):
        artifact_rows = by_artifact_id[artifact_id]
        artifact_summaries.append(
            {
                "artifact_id": artifact_id,
                "entity_count": len(artifact_rows),
                "blocked_entity_count": sum(1 for row in artifact_rows if row["ambiguity_status"] != "resolved"),
                "entity_ids": _distinct([row["entity_id"] for row in artifact_rows]),
            }
        )

    canonical_entity_count = sum(1 for row in canonical_entities if not row["ambiguity_blocked"])
    blocked_entity_count = sum(1 for row in canonical_entities if row["ambiguity_blocked"])
    cross_artifact_entity_count = sum(
        1 for row in canonical_entities if len(row["source_artifact_ids"]) > 1
    )

    if not entries or str(memory_summary.get("final_recommendation") or "") != "research_memory_coverage_ready":
        graph_status = "blocked"
    elif blocked_entity_count:
        graph_status = "partial"
    else:
        graph_status = "ready"

    summary = {
        "memory_entry_count": len([row for row in entries if isinstance(row, Mapping)]),
        "observation_count": len(observations),
        "canonical_entity_count": canonical_entity_count,
        "blocked_entity_count": blocked_entity_count,
        "cross_artifact_entity_count": cross_artifact_entity_count,
        "artifact_count": len(artifact_summaries),
        "graph_status": graph_status,
        "final_recommendation": (
            "entity_resolution_hardening_ready"
            if graph_status == "ready"
            else "entity_resolution_hardening_partial"
            if graph_status == "partial"
            else "entity_resolution_hardening_blocked"
        ),
        "operator_summary": (
            "Canonical entity resolution is deterministic context only. Cross-artifact label or "
            "type ambiguity remains blocked and does not authorize escalation."
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": summary,
        "canonical_entities": canonical_entities,
        "blocked_entities": blocked_entities,
        "artifact_summaries": artifact_summaries,
        "entity_observations": observations,
        "checks": {
            "cross_artifact_entities": [
                row for row in canonical_entities if len(row["source_artifact_ids"]) > 1
            ],
            "blocked_entities": blocked_entities,
        },
        "supporting_reports": {
            "qre_research_memory_coverage": "logs/qre_research_memory_coverage/latest.json",
        },
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
            "identity_is_infrastructure_only": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    blocked_rows = report.get("blocked_entities") if isinstance(report.get("blocked_entities"), list) else []
    canonical_rows = report.get("canonical_entities") if isinstance(report.get("canonical_entities"), list) else []
    return "\n".join(
        [
            "# QRE Entity Resolution Hardening",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["graph_status", str(summary.get("graph_status") or "")],
                    ["memory_entry_count", str(summary.get("memory_entry_count") or 0)],
                    ["observation_count", str(summary.get("observation_count") or 0)],
                    ["canonical_entity_count", str(summary.get("canonical_entity_count") or 0)],
                    ["blocked_entity_count", str(summary.get("blocked_entity_count") or 0)],
                    ["cross_artifact_entity_count", str(summary.get("cross_artifact_entity_count") or 0)],
                ],
            ),
            "",
            "## Blocked entities",
            _table(
                ["entity_id", "artifact_ids", "reason"],
                [
                    [
                        str(row.get("entity_id") or ""),
                        ", ".join(str(value) for value in row.get("artifact_ids") or []),
                        str(row.get("reason") or ""),
                    ]
                    for row in blocked_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
            "## Canonical entities",
            _table(
                ["entity_id", "entity_type", "labels", "artifacts", "blocked"],
                [
                    [
                        str(row.get("entity_id") or ""),
                        str(row.get("canonical_entity_type") or ""),
                        ", ".join(str(value) for value in row.get("distinct_labels") or []) or "-",
                        ", ".join(str(value) for value in row.get("source_artifact_ids") or []) or "-",
                        str(bool(row.get("ambiguity_blocked"))),
                    ]
                    for row in canonical_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_entity_resolution_hardening: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_summary, summary)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_entity_resolution_hardening",
        description="Materialize the read-only QRE entity resolution hardening report.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_entity_resolution_hardening(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
