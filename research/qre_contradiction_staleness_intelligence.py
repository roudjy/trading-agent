from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_lineage_graph_v1 as lineage_graph
from research import qre_research_memory_graph as memory_graph
from research import qre_research_memory_retrieval as memory_retrieval
from research import qre_retrieval_maturity as retrieval_maturity
from research import qre_trusted_loop_operational_controls as operational_controls


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_contradiction_staleness_intelligence"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_contradiction_staleness_intelligence")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_contradiction_staleness_intelligence/"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        canonical = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if canonical in seen:
            continue
        seen.add(canonical)
        deduped.append(dict(row))
    return deduped


def _query_rows(report: Mapping[str, Any], query_id: str) -> list[dict[str, Any]]:
    queries = report.get("queries") if isinstance(report.get("queries"), list) else []
    for query in queries:
        if not isinstance(query, Mapping):
            continue
        if _text(query.get("query_id")) != query_id:
            continue
        rows = query.get("rows") if isinstance(query.get("rows"), list) else []
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def build_contradiction_staleness_intelligence(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    retrieval_report = memory_retrieval.build_research_memory_retrieval(repo_root=repo_root)
    memory_graph_report = memory_graph.build_research_memory_graph(repo_root=repo_root)
    lineage_graph_report = lineage_graph.build_qre_lineage_graph_v1(repo_root=repo_root)
    maturity_report = retrieval_maturity.build_retrieval_maturity(repo_root=repo_root)
    operational_report = operational_controls.build_trusted_loop_operational_controls(
        repo_root=repo_root
    )

    contradiction_rows: list[dict[str, Any]] = []
    contradiction_rows.extend(
        {
            "source": "qre_research_memory_retrieval",
            "detail": _text(row.get("reason")) or _text(row.get("scope_key")),
            "scope_key": _text(row.get("scope_key")),
            "dimension": _text(row.get("dimension")),
            "artifact_ref": "logs/qre_research_memory_retrieval/latest.json",
        }
        for row in _query_rows(retrieval_report, "contradictory_outcomes")
    )
    checks = memory_graph_report.get("checks") if isinstance(memory_graph_report.get("checks"), Mapping) else {}
    contradiction_rows.extend(
        {
            "source": "qre_research_memory_graph",
            "detail": _text(row.get("reason")),
            "scope_key": _text(row.get("subject_id")),
            "dimension": "memory_subject",
            "artifact_ref": "logs/qre_research_memory_graph/latest.json",
        }
        for row in (checks.get("contradictions") or [])
        if isinstance(row, Mapping)
    )
    lineage_checks = lineage_graph_report.get("checks") if isinstance(lineage_graph_report.get("checks"), Mapping) else {}
    contradiction_rows.extend(
        {
            "source": "qre_lineage_graph_v1",
            "detail": _text(row.get("detail")) or _text(row.get("kind")),
            "scope_key": _text(row.get("campaign_id")) or _text(row.get("hypothesis_id")),
            "dimension": _text(row.get("kind")) or "lineage_graph",
            "artifact_ref": "logs/qre_lineage_graph_v1/latest.json",
        }
        for row in (lineage_checks.get("contradictions") or [])
        if isinstance(row, Mapping)
    )
    contradiction_rows = _dedupe_rows(contradiction_rows)

    stale_rows: list[dict[str, Any]] = []
    stale_rows.extend(
        {
            "source": "qre_research_memory_retrieval",
            "detail": _text(row.get("status")),
            "artifact_path": _text(row.get("artifact_path")),
            "artifact_ref": "logs/qre_research_memory_retrieval/latest.json",
        }
        for row in _query_rows(retrieval_report, "stale_or_superseded_knowledge")
    )
    reconciliation = (
        operational_report.get("state_reconciliation")
        if isinstance(operational_report.get("state_reconciliation"), Mapping)
        else {}
    )
    stale_rows.extend(
        {
            "source": "qre_trusted_loop_operational_controls",
            "detail": _text(reason),
            "artifact_path": "research/run_manifest_latest.v1.json",
            "artifact_ref": "logs/qre_trusted_loop_operational_controls/latest.json",
        }
        for reason in reconciliation.get("mismatches") or []
        if _text(reason)
    )
    freshness = (
        operational_report.get("artifact_freshness")
        if isinstance(operational_report.get("artifact_freshness"), Mapping)
        else {}
    )
    stale_rows.extend(
        {
            "source": "qre_trusted_loop_operational_controls",
            "detail": _text(reason),
            "artifact_path": "research/run_state.v1.json",
            "artifact_ref": "logs/qre_trusted_loop_operational_controls/latest.json",
        }
        for reason in freshness.get("stale_reasons") or []
        if _text(reason)
    )
    stale_rows = _dedupe_rows(stale_rows)

    graph_statuses = {
        "research_memory_graph": _text((memory_graph_report.get("summary") or {}).get("graph_status")),
        "lineage_graph": _text((lineage_graph_report.get("summary") or {}).get("graph_status")),
        "retrieval_maturity": _text((maturity_report.get("summary") or {}).get("graph_status")),
    }
    ready = all(status in {"ready", "partial"} for status in graph_statuses.values()) and bool(
        (retrieval_report.get("summary") or {}).get("research_memory_ready")
    )
    exact_next_action = (
        "reconcile_stale_or_superseded_artifacts"
        if stale_rows
        else "review_visible_contradictions_before_new_research"
        if contradiction_rows
        else "preserve_contradiction_and_staleness_visibility"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "contradiction_staleness_ready": ready,
            "contradiction_count": len(contradiction_rows),
            "stale_or_superseded_count": len(stale_rows),
            "graph_statuses": graph_statuses,
            "exact_next_action": exact_next_action,
            "operator_summary": (
                "Contradiction and staleness intelligence unifies retrieval, research-memory graph, "
                "lineage graph, retrieval maturity, and trusted-loop stale-artifact context as "
                "read-only operator visibility only."
            ),
        },
        "contradictions": contradiction_rows,
        "stale_or_superseded": stale_rows,
        "supporting_reports": {
            "qre_research_memory_retrieval": "logs/qre_research_memory_retrieval/latest.json",
            "qre_research_memory_graph": "logs/qre_research_memory_graph/latest.json",
            "qre_lineage_graph_v1": "logs/qre_lineage_graph_v1/latest.json",
            "qre_retrieval_maturity": "logs/qre_retrieval_maturity/latest.json",
            "qre_trusted_loop_operational_controls": "logs/qre_trusted_loop_operational_controls/latest.json",
        },
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
            "can_activate_shadow": False,
        },
        "safety_invariants": {
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(
        {
            "schema_version": report["schema_version"],
            "report_kind": report["report_kind"],
            "summary": report["summary"],
            "contradictions": report["contradictions"],
            "stale_or_superseded": report["stale_or_superseded"],
            "supporting_reports": report["supporting_reports"],
            "authority_boundary": report["authority_boundary"],
        }
    )
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    lines = [
        "# QRE Contradiction And Staleness Intelligence",
        "",
        f"- contradiction_staleness_ready: {summary.get('contradiction_staleness_ready', False)}",
        f"- contradiction_count: {summary.get('contradiction_count', 0)}",
        f"- stale_or_superseded_count: {summary.get('stale_or_superseded_count', 0)}",
        f"- exact_next_action: {summary.get('exact_next_action', '')}",
        "",
        "## Graph Statuses",
    ]
    for key, value in (summary.get("graph_statuses") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    retrieval_payload = memory_retrieval.build_research_memory_retrieval(repo_root=repo_root)
    memory_retrieval.write_outputs(retrieval_payload, repo_root=repo_root)
    memory_graph_payload = memory_graph.build_research_memory_graph(repo_root=repo_root)
    memory_graph.write_outputs(memory_graph_payload, repo_root=repo_root)
    lineage_payload = lineage_graph.build_qre_lineage_graph_v1(repo_root=repo_root)
    lineage_graph.write_outputs(lineage_payload, repo_root=repo_root)
    maturity_payload = retrieval_maturity.build_retrieval_maturity(repo_root=repo_root)
    retrieval_maturity.write_outputs(maturity_payload, repo_root=repo_root)

    refreshed = build_contradiction_staleness_intelligence(repo_root=repo_root)
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(refreshed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(refreshed) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_contradiction_staleness_intelligence",
        description="Materialize deterministic contradiction and staleness visibility across QRE retrieval and graph surfaces.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_contradiction_staleness_intelligence()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
