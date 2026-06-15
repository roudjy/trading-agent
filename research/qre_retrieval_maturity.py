from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_research_memory_coverage as memory_coverage
from research import qre_research_memory_graph as memory_graph


REPORT_KIND: Final[str] = "qre_retrieval_maturity"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_retrieval_maturity")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_retrieval_maturity/"
DEFAULT_QUERY: Final[str] = "policy action"
RRF_K: Final[int] = 60


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


def _flatten(value: Any) -> str:
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            parts.append(str(key))
            parts.append(_flatten(item))
        return " ".join(part for part in parts if part)
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _entry_fields(entry: Mapping[str, Any]) -> str:
    ontology = entry.get("ontology_classification")
    if not isinstance(ontology, Mapping):
        ontology = {}
    return " ".join(
        part
        for part in (
            str(entry.get("artifact_id") or ""),
            str(entry.get("subject_id") or ""),
            str(entry.get("record_kind") or ""),
            str(entry.get("title") or ""),
            str(entry.get("text_preview") or ""),
            _flatten(entry.get("metadata") or {}),
            _flatten(ontology),
        )
        if part
    )


def _keyword_score(entry: Mapping[str, Any], query_tokens: set[str]) -> int:
    haystack = _tokens(_entry_fields(entry))
    return len(query_tokens & set(haystack))


def _metadata_score(entry: Mapping[str, Any], query_tokens: set[str]) -> int:
    metadata = entry.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    ontology = entry.get("ontology_classification")
    if not isinstance(ontology, Mapping):
        ontology = {}
    haystack = set(_tokens(_flatten(metadata) + " " + _flatten(ontology)))
    return len(query_tokens & haystack)


def _graph_score(
    *,
    graph: Mapping[str, Any],
    seed_subject_ids: set[str],
    seed_node_ids: set[str],
    candidate_node_ids: set[str],
) -> dict[str, int]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    node_subject: dict[str, str] = {}
    retrieval_nodes_by_subject: defaultdict[str, list[str]] = defaultdict(list)
    node_types: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("node_id") or "")
        node_types[node_id] = str(node.get("node_type") or "")
        subject_id = str(node.get("subject_id") or "")
        if subject_id:
            node_subject[node_id] = subject_id
        if node_id.startswith("retrieval::") and subject_id:
            retrieval_nodes_by_subject[subject_id].append(node_id)

    scores: dict[str, int] = defaultdict(int)
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        relation = str(edge.get("relation") or "")
        if relation == "same_subject":
            if source in seed_node_ids and target in candidate_node_ids:
                scores[target] += 3
            if target in seed_node_ids and source in candidate_node_ids:
                scores[source] += 3
        elif relation == "contradiction_visible":
            if source in seed_node_ids and target in candidate_node_ids:
                scores[target] += 1
            if target in seed_node_ids and source in candidate_node_ids:
                scores[source] += 1

    for subject_id in seed_subject_ids:
        for retrieval_node in retrieval_nodes_by_subject.get(subject_id, []):
            for edge in edges:
                if not isinstance(edge, Mapping):
                    continue
                if str(edge.get("source") or "") != retrieval_node:
                    continue
                if str(edge.get("relation") or "") != "retrieval_similarity":
                    continue
                target = str(edge.get("target") or "")
                if target in candidate_node_ids:
                    scores[target] += 2

    return dict(scores)


def _rrf(surface: Sequence[str], *, rrf_k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rank, node_id in enumerate(surface, start=1):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (rrf_k + rank)
    return scores


def build_retrieval_maturity(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
    query: str = DEFAULT_QUERY,
) -> dict[str, Any]:
    memory = memory_coverage.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    graph = memory_graph.build_research_memory_graph(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    memory_summary = memory.get("summary") if isinstance(memory.get("summary"), Mapping) else {}
    graph_summary = graph.get("summary") if isinstance(graph.get("summary"), Mapping) else {}
    entries = memory.get("entries") if isinstance(memory.get("entries"), list) else []
    query_tokens = set(_tokens(query))

    by_node_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        node_id = f"memory::{entry.get('artifact_id') or ''}"
        by_node_id[node_id] = {
            "node_id": node_id,
            "artifact_id": str(entry.get("artifact_id") or ""),
            "subject_id": str(entry.get("subject_id") or ""),
            "record_kind": str(entry.get("record_kind") or ""),
            "title": str(entry.get("title") or ""),
            "text_preview": str(entry.get("text_preview") or ""),
            "metadata": dict(entry.get("metadata") or {}),
            "ontology_classification": dict(entry.get("ontology_classification") or {}),
        }

    keyword_scores = {
        node_id: _keyword_score(entry, query_tokens)
        for node_id, entry in by_node_id.items()
    }
    metadata_scores = {
        node_id: _metadata_score(entry, query_tokens)
        for node_id, entry in by_node_id.items()
    }
    keyword_ranked = sorted(
        [item for item in by_node_id.items() if keyword_scores[item[0]] > 0],
        key=lambda item: (-keyword_scores[item[0]], item[1]["artifact_id"]),
    )
    metadata_ranked = sorted(
        [item for item in by_node_id.items() if metadata_scores[item[0]] > 0],
        key=lambda item: (-metadata_scores[item[0]], item[1]["artifact_id"]),
    )

    seed_node_ids = {
        node_id
        for node_id, _entry in (keyword_ranked[:5] + metadata_ranked[:5])
    }
    seed_subject_ids = {
        by_node_id[node_id]["subject_id"]
        for node_id in seed_node_ids
        if by_node_id[node_id]["subject_id"]
    }
    candidate_node_ids = set(by_node_id)
    graph_scores = _graph_score(
        graph=graph,
        seed_subject_ids=seed_subject_ids,
        seed_node_ids=seed_node_ids,
        candidate_node_ids=candidate_node_ids,
    )
    graph_ranked = sorted(
        [item for item in by_node_id.items() if graph_scores.get(item[0], 0) > 0],
        key=lambda item: (-graph_scores.get(item[0], 0), item[1]["artifact_id"]),
    )

    combined_scores: defaultdict[str, float] = defaultdict(float)
    for node_id, score in _rrf([node_id for node_id, _entry in keyword_ranked]).items():
        combined_scores[node_id] += score
    for node_id, score in _rrf([node_id for node_id, _entry in metadata_ranked]).items():
        combined_scores[node_id] += score
    for node_id, score in _rrf([node_id for node_id, _entry in graph_ranked]).items():
        combined_scores[node_id] += score

    combined_ranked = sorted(
        (
            {
                "artifact_id": entry["artifact_id"],
                "subject_id": entry["subject_id"],
                "record_kind": entry["record_kind"],
                "title": entry["title"],
                "keyword_score": keyword_scores[node_id],
                "metadata_score": metadata_scores[node_id],
                "graph_score": graph_scores.get(node_id, 0),
                "rrf_score": round(combined_scores.get(node_id, 0.0), 10),
                "seeded_by_keyword": node_id in {item[0] for item in keyword_ranked[:5]},
                "seeded_by_metadata": node_id in {item[0] for item in metadata_ranked[:5]},
                "graph_neighbor_visible": graph_scores.get(node_id, 0) > 0,
            }
            for node_id, entry in by_node_id.items()
            if combined_scores.get(node_id, 0.0) > 0
        ),
        key=lambda row: (-float(row["rrf_score"]), str(row["artifact_id"])),
    )

    keyword_top_ids = [node_id for node_id, _entry in keyword_ranked[:5]]
    metadata_top_ids = [node_id for node_id, _entry in metadata_ranked[:5]]
    graph_top_ids = [node_id for node_id, _entry in graph_ranked[:5]]

    if not entries or str(memory_summary.get("final_recommendation") or "") != "research_memory_coverage_ready":
        status = "blocked"
    elif not graph_summary or str(graph_summary.get("graph_status") or "") == "blocked":
        status = "partial"
    elif not keyword_top_ids or not metadata_top_ids or not graph_top_ids:
        status = "partial"
    else:
        status = "ready"

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "query": query,
        "summary": {
            "memory_entry_count": len([row for row in entries if isinstance(row, Mapping)]),
            "keyword_surface_count": len(keyword_ranked),
            "metadata_surface_count": len(metadata_ranked),
            "graph_neighbor_surface_count": len(graph_ranked),
            "combined_result_count": len(combined_ranked),
            "graph_status": status,
            "final_recommendation": (
                "retrieval_maturity_ready"
                if status == "ready"
                else "retrieval_maturity_partial"
                if status == "partial"
                else "retrieval_maturity_blocked"
            ),
            "operator_summary": (
                "Keyword, metadata, and graph-neighbor retrieval are combined with deterministic "
                "RRF scoring as context only. Retrieval never becomes promotion authority."
            ),
        },
        "keyword_surface": [
            {
                "artifact_id": entry["artifact_id"],
                "subject_id": entry["subject_id"],
                "record_kind": entry["record_kind"],
                "title": entry["title"],
                "score": keyword_scores[node_id],
            }
            for node_id, entry in keyword_ranked
        ],
        "metadata_surface": [
            {
                "artifact_id": entry["artifact_id"],
                "subject_id": entry["subject_id"],
                "record_kind": entry["record_kind"],
                "title": entry["title"],
                "score": metadata_scores[node_id],
            }
            for node_id, entry in metadata_ranked
        ],
        "graph_neighbor_surface": [
            {
                "artifact_id": entry["artifact_id"],
                "subject_id": entry["subject_id"],
                "record_kind": entry["record_kind"],
                "title": entry["title"],
                "score": graph_scores[node_id],
            }
            for node_id, entry in graph_ranked
        ],
        "combined_results": combined_ranked,
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
            "retrieval_is_context_only": True,
        },
        "supporting_reports": {
            "qre_research_memory_coverage": "logs/qre_research_memory_coverage/latest.json",
            "qre_research_memory_graph": "logs/qre_research_memory_graph/latest.json",
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    combined_rows = report.get("combined_results") if isinstance(report.get("combined_results"), list) else []
    return "\n".join(
        [
            "# QRE Retrieval Maturity",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["query", str(report.get("query") or "")],
                    ["graph_status", str(summary.get("graph_status") or "")],
                    ["memory_entry_count", str(summary.get("memory_entry_count") or 0)],
                    ["keyword_surface_count", str(summary.get("keyword_surface_count") or 0)],
                    ["metadata_surface_count", str(summary.get("metadata_surface_count") or 0)],
                    ["graph_neighbor_surface_count", str(summary.get("graph_neighbor_surface_count") or 0)],
                    ["combined_result_count", str(summary.get("combined_result_count") or 0)],
                ],
            ),
            "",
            "## Combined results",
            _table(
                ["artifact_id", "keyword", "metadata", "graph", "rrf", "subject_id"],
                [
                    [
                        str(row.get("artifact_id") or ""),
                        str(row.get("keyword_score") or 0),
                        str(row.get("metadata_score") or 0),
                        str(row.get("graph_score") or 0),
                        str(row.get("rrf_score") or 0.0),
                        str(row.get("subject_id") or ""),
                    ]
                    for row in combined_rows
                    if isinstance(row, Mapping)
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_retrieval_maturity: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_retrieval_maturity",
        description="Materialize the deterministic QRE retrieval maturity report.",
    )
    parser.add_argument("--query", type=str, default=DEFAULT_QUERY)
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_retrieval_maturity(
        query=args.query,
        max_candidates=args.max_candidates,
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
