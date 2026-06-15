from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_research_memory_coverage as memory_coverage


REPORT_KIND: Final[str] = "qre_research_memory_graph"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_memory_graph")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_research_memory_graph/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    node_id = str(node["node_id"])
    if node_id not in nodes:
        nodes[node_id] = node


def _add_edge(
    edges: list[dict[str, Any]],
    *,
    source: str,
    target: str,
    relation: str,
    evidence_refs: Sequence[str] = (),
) -> None:
    edges.append(
        {
            "edge_id": f"{source}->{target}:{relation}",
            "source": source,
            "target": target,
            "relation": relation,
            "evidence_refs": list(evidence_refs),
        }
    )


def _is_contradiction_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("contradiction", "inconsistent", "conflict"))


def _text_from_entry(entry: Mapping[str, Any]) -> str:
    parts = [str(entry.get("artifact_id") or ""), str(entry.get("title") or ""), str(entry.get("text_preview") or "")]
    metadata = entry.get("metadata")
    if isinstance(metadata, Mapping):
        parts.extend(str(value) for value in metadata.values())
        reason_codes = metadata.get("reason_codes")
        if isinstance(reason_codes, Sequence) and not isinstance(reason_codes, str):
            parts.extend(str(value) for value in reason_codes)
    return " ".join(part for part in parts if part)


def build_research_memory_graph(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
    top_k: int = 3,
) -> dict[str, Any]:
    memory = memory_coverage.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    retrieval = memory_coverage.build_failure_retrieval(memory, top_k=top_k)

    memory_summary = memory.get("summary") if isinstance(memory.get("summary"), Mapping) else {}
    retrieval_summary = retrieval.get("summary") if isinstance(retrieval.get("summary"), Mapping) else {}

    entries = memory.get("entries") if isinstance(memory.get("entries"), list) else []
    retrieval_rows = retrieval.get("rows") if isinstance(retrieval.get("rows"), list) else []

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    orphan_nodes: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    contradiction_artifacts: set[str] = set()
    subject_nodes: dict[str, str] = {}
    subject_entry_nodes: defaultdict[str, list[str]] = defaultdict(list)

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        artifact_id = str(entry.get("artifact_id") or "")
        subject_id = str(entry.get("subject_id") or "")
        node_id = f"memory::{artifact_id}"
        subject_node_id = f"subject::{subject_id}" if subject_id else ""
        subject_nodes.setdefault(subject_id, subject_node_id)
        subject_entry_nodes[subject_id].append(node_id)

        ontology = entry.get("ontology_classification")
        if not isinstance(ontology, Mapping):
            ontology = {}
        _add_node(
            nodes,
            {
                "node_id": node_id,
                "node_type": "memory_entry",
                "lineage_layer": "memory_entry",
                "label": str(entry.get("title") or artifact_id),
                "artifact_id": artifact_id,
                "subject_id": subject_id,
                "record_kind": entry.get("record_kind"),
                "ontology_scope": ontology.get("research_scope"),
                "ontology_readiness": ontology.get("readiness_state"),
                "ontology_asset_class": ontology.get("asset_class"),
            },
        )
        if subject_node_id:
            _add_node(
                nodes,
                {
                    "node_id": subject_node_id,
                    "node_type": "subject",
                    "lineage_layer": "subject",
                    "label": subject_id,
                },
            )
            _add_edge(
                edges,
                source=subject_node_id,
                target=node_id,
                relation="contains_entry",
                evidence_refs=["logs/qre_research_memory_coverage/latest.json"],
            )

    # Same-subject edges keep the graph explicit and deterministic.
    for subject_id, node_ids in sorted(subject_entry_nodes.items()):
        node_ids = sorted(set(node_ids))
        for left in range(len(node_ids)):
            for right in range(left + 1, len(node_ids)):
                _add_edge(
                    edges,
                    source=node_ids[left],
                    target=node_ids[right],
                    relation="same_subject",
                    evidence_refs=["logs/qre_research_memory_coverage/latest.json"],
                )

    retrieval_by_subject = {
        str(row.get("subject_id") or ""): row
        for row in retrieval_rows
        if isinstance(row, Mapping)
    }
    for subject_id, row in retrieval_by_subject.items():
        subject_node_id = subject_nodes.get(subject_id, "")
        retrieval_node_id = f"retrieval::{subject_id}"
        _add_node(
            nodes,
            {
                "node_id": retrieval_node_id,
                "node_type": "retrieval_result",
                "lineage_layer": "retrieval",
                "label": subject_id,
                "subject_id": subject_id,
                "blocker_code": row.get("blocker_code"),
                "recommended_action": row.get("recommended_action"),
            },
        )
        if subject_node_id:
            _add_edge(
                edges,
                source=subject_node_id,
                target=retrieval_node_id,
                relation="retrieval_summary",
                evidence_refs=["logs/qre_failure_retrieval/latest.json"],
            )
        for match in row.get("similar_failures") or []:
            if not isinstance(match, Mapping):
                continue
            match_subject = str(match.get("subject_id") or "")
            match_node_id = f"memory::failure:{match.get('artifact_id') or match_subject}"
            _add_edge(
                edges,
                source=retrieval_node_id,
                target=match_node_id,
                relation="retrieval_similarity",
                evidence_refs=["logs/qre_failure_retrieval/latest.json"],
            )

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        artifact_id = str(entry.get("artifact_id") or "")
        node_id = f"memory::{artifact_id}"
        text = _text_from_entry(entry)
        metadata = entry.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}

        contradiction_hit = _is_contradiction_marker(text)
        if contradiction_hit:
            contradiction_node_id = f"contradiction::{artifact_id}"
            if artifact_id not in contradiction_artifacts:
                contradiction_artifacts.add(artifact_id)
                _add_node(
                    nodes,
                    {
                        "node_id": contradiction_node_id,
                        "node_type": "contradiction",
                        "lineage_layer": "contradiction",
                        "label": artifact_id,
                        "subject_id": entry.get("subject_id"),
                        "source_artifact_id": artifact_id,
                        "reason_codes": list(metadata.get("reason_codes") or []),
                    },
                )
                _add_edge(
                    edges,
                    source=node_id,
                    target=contradiction_node_id,
                    relation="contradiction_visible",
                    evidence_refs=["logs/qre_research_memory_coverage/latest.json"],
                )
                contradictions.append(
                    {
                        "contradiction_id": contradiction_node_id,
                        "subject_id": entry.get("subject_id"),
                        "artifact_id": artifact_id,
                        "reason": "contradiction_marker_present_in_memory_entry",
                    }
                )

        if str(entry.get("record_kind") or "") == "reason_record":
            reason_codes = [str(code) for code in metadata.get("reason_codes") or []]
            if any(_is_contradiction_marker(code) for code in reason_codes):
                contradiction_node_id = f"contradiction::{artifact_id}"
                if artifact_id not in contradiction_artifacts:
                    contradiction_artifacts.add(artifact_id)
                    _add_node(
                        nodes,
                        {
                            "node_id": contradiction_node_id,
                            "node_type": "contradiction",
                            "lineage_layer": "contradiction",
                            "label": artifact_id,
                            "subject_id": entry.get("subject_id"),
                            "source_artifact_id": artifact_id,
                            "reason_codes": reason_codes,
                        },
                    )
                    _add_edge(
                        edges,
                        source=node_id,
                        target=contradiction_node_id,
                        relation="contradiction_visible",
                        evidence_refs=["logs/qre_research_memory_coverage/latest.json"],
                    )
                    contradictions.append(
                        {
                            "contradiction_id": contradiction_node_id,
                            "subject_id": entry.get("subject_id"),
                            "artifact_id": artifact_id,
                            "reason": "contradictory_reason_code_visible",
                        }
                    )

    subject_counts = Counter(str(entry.get("subject_id") or "") for entry in entries if isinstance(entry, Mapping))
    for node in nodes.values():
        layer = str(node.get("lineage_layer") or "")
        if layer == "memory_entry":
            node_id = str(node.get("node_id") or "")
            if not any(edge["source"] == node_id or edge["target"] == node_id for edge in edges):
                orphan_nodes.append(
                    {
                        "node_id": node_id,
                        "lineage_layer": layer,
                        "reason": "memory_entry_has_no_graph_edges",
                    }
                )
        elif layer == "subject":
            subject_id = str(node.get("label") or "")
            if subject_counts.get(subject_id, 0) == 0:
                orphan_nodes.append(
                    {
                        "node_id": str(node.get("node_id") or ""),
                        "lineage_layer": layer,
                        "reason": "subject_has_no_memory_entries",
                    }
                )
        elif layer == "retrieval":
            node_id = str(node.get("node_id") or "")
            if not any(edge["source"] == node_id or edge["target"] == node_id for edge in edges):
                orphan_nodes.append(
                    {
                        "node_id": node_id,
                        "lineage_layer": layer,
                        "reason": "retrieval_result_has_no_matches",
                    }
                )

    if not entries or str(memory_summary.get("final_recommendation") or "") != "research_memory_coverage_ready":
        graph_status = "blocked"
    elif contradictions:
        graph_status = "partial"
    elif orphan_nodes:
        graph_status = "partial"
    else:
        graph_status = "ready"

    node_type_counts = Counter(str(node.get("node_type") or "") for node in nodes.values())
    edge_relation_counts = Counter(str(edge.get("relation") or "") for edge in edges)

    summary = {
        "memory_entry_count": len([row for row in entries if isinstance(row, Mapping)]),
        "subject_count": len(subject_counts),
        "retrieval_subject_count": len(retrieval_by_subject),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "orphan_count": len(orphan_nodes),
        "contradiction_count": len(contradictions),
        "graph_status": graph_status,
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_relation_counts": dict(sorted(edge_relation_counts.items())),
        "operator_summary": (
            "Research memory graph is a deterministic context layer over current entries, retrieval, and "
            "contradiction visibility. It is read-only and does not certify truth or alpha authority."
        ),
    }

    nodes_list = sorted(nodes.values(), key=lambda row: (str(row.get("lineage_layer") or ""), str(row.get("node_id") or "")))
    edges.sort(key=lambda row: (str(row["relation"]), str(row["source"]), str(row["target"])))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": summary,
        "nodes": nodes_list,
        "edges": edges,
        "checks": {
            "orphan_nodes": orphan_nodes,
            "contradictions": contradictions,
        },
        "supporting_reports": {
            "qre_research_memory_coverage": "logs/qre_research_memory_coverage/latest.json",
            "qre_failure_retrieval": "logs/qre_failure_retrieval/latest.json",
        },
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), Mapping) else {}
    orphan_rows = checks.get("orphan_nodes") if isinstance(checks.get("orphan_nodes"), list) else []
    contradiction_rows = checks.get("contradictions") if isinstance(checks.get("contradictions"), list) else []
    return "\n".join(
        [
            "# QRE Research Memory Graph",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["graph_status", str(summary.get("graph_status") or "")],
                    ["memory_entry_count", str(summary.get("memory_entry_count") or 0)],
                    ["subject_count", str(summary.get("subject_count") or 0)],
                    ["retrieval_subject_count", str(summary.get("retrieval_subject_count") or 0)],
                    ["node_count", str(summary.get("node_count") or 0)],
                    ["edge_count", str(summary.get("edge_count") or 0)],
                    ["orphan_count", str(summary.get("orphan_count") or 0)],
                    ["contradiction_count", str(summary.get("contradiction_count") or 0)],
                ],
            ),
            "",
            "## Orphans",
            _table(
                ["node_id", "layer", "reason"],
                [
                    [
                        str(row.get("node_id") or ""),
                        str(row.get("lineage_layer") or ""),
                        str(row.get("reason") or ""),
                    ]
                    for row in orphan_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
            "## Contradictions",
            _table(
                ["contradiction_id", "subject_id", "reason"],
                [
                    [
                        str(row.get("contradiction_id") or ""),
                        str(row.get("subject_id") or ""),
                        str(row.get("reason") or ""),
                    ]
                    for row in contradiction_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_research_memory_graph: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_research_memory_graph",
        description="Materialize the read-only QRE research memory graph.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_research_memory_graph(max_candidates=args.max_candidates, top_k=args.top_k)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
