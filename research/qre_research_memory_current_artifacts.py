from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_research import research_memory
from research import qre_campaign_throughput_bottleneck_intelligence as throughput_bottlenecks
from research import qre_contradiction_staleness_intelligence as contradiction_staleness
from research import qre_experiment_dedup_novelty_enforcement as novelty_enforcement
from research import qre_read_only_artifact_continuity as artifact_continuity
from research import qre_research_memory_coverage as memory_coverage


REPORT_KIND: Final[str] = "qre_research_memory_current_artifacts"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_memory_current_artifacts")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_research_memory_current_artifacts/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_research_memory_current_artifacts(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    package_status = research_memory.read_research_memory_status(
        output_dir=Path("logs/qre_research_memory"),
        repo_root=repo_root,
    )
    memory = memory_coverage.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    retrieval = memory_coverage.build_failure_retrieval(memory)

    memory_summary = memory.get("summary") if isinstance(memory.get("summary"), Mapping) else {}
    retrieval_summary = (
        retrieval.get("summary") if isinstance(retrieval.get("summary"), Mapping) else {}
    )
    package_ready = bool(package_status.get("research_memory_ready"))
    coverage_ready = (
        str(memory_summary.get("final_recommendation") or "") == "research_memory_coverage_ready"
    )
    retrieval_ready = (
        str(retrieval_summary.get("final_recommendation") or "") == "failure_retrieval_ready"
    )
    continuity = artifact_continuity.build_read_only_artifact_continuity(repo_root=repo_root)
    continuity_summary = continuity.get("summary") if isinstance(continuity.get("summary"), Mapping) else {}
    continuity_ready = bool(continuity_summary.get("artifact_continuity_ready"))
    contradiction_report = contradiction_staleness.build_contradiction_staleness_intelligence(repo_root=repo_root)
    contradiction_summary = (
        contradiction_report.get("summary") if isinstance(contradiction_report.get("summary"), Mapping) else {}
    )
    contradiction_ready = bool(contradiction_summary.get("contradiction_staleness_ready"))
    throughput_report = throughput_bottlenecks.build_campaign_throughput_bottleneck_intelligence(
        repo_root=repo_root
    )
    throughput_summary = (
        throughput_report.get("summary") if isinstance(throughput_report.get("summary"), Mapping) else {}
    )
    throughput_ready = bool(
        throughput_summary.get("campaign_throughput_bottleneck_intelligence_ready")
    )
    novelty_report = novelty_enforcement.build_experiment_dedup_novelty_enforcement(
        repo_root=repo_root
    )
    novelty_summary = (
        novelty_report.get("summary") if isinstance(novelty_report.get("summary"), Mapping) else {}
    )
    novelty_ready = bool(novelty_summary.get("experiment_dedup_novelty_enforcement_ready"))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "package_research_memory_status": str(package_status.get("status") or "unknown"),
            "package_research_memory_ready": package_ready,
            "coverage_ready": coverage_ready,
            "retrieval_ready": retrieval_ready,
            "artifact_continuity_ready": continuity_ready,
            "contradiction_staleness_ready": contradiction_ready,
            "campaign_throughput_bottleneck_intelligence_ready": throughput_ready,
            "experiment_dedup_novelty_enforcement_ready": novelty_ready,
            "indexed_entry_count": int(memory_summary.get("indexed_entry_count") or 0),
            "indexed_candidate_count": int(memory_summary.get("indexed_candidate_count") or 0),
            "retrievable_failure_subject_count": int(
                retrieval_summary.get("retrievable_failure_subject_count") or 0
            ),
            "artifact_continuity_materializable_target_count": int(
                continuity_summary.get("materializable_target_count") or 0
            ),
            "visible_contradiction_count": int(contradiction_summary.get("contradiction_count") or 0),
            "visible_stale_or_superseded_count": int(
                contradiction_summary.get("stale_or_superseded_count") or 0
            ),
            "visible_campaign_throughput_bottleneck_count": int(
                throughput_summary.get("bottleneck_count") or 0
            ),
            "visible_experiment_duplicate_pressure_count": int(
                novelty_summary.get("duplicate_pressure_count") or 0
            ),
            "final_recommendation": (
                "research_memory_current_artifacts_ready"
                if package_ready
                and coverage_ready
                and retrieval_ready
                and continuity_ready
                and contradiction_ready
                and throughput_ready
                and novelty_ready
                else "research_memory_current_artifacts_partial"
            ),
            "operator_summary": (
                "Current research-memory artifacts are materialized from existing read-only package and QRE "
                "memory surfaces without adding retrieval authority or runtime behavior."
            ),
        },
        "package_status": dict(package_status),
        "memory_coverage_summary": dict(memory_summary),
        "failure_retrieval_summary": dict(retrieval_summary),
        "artifact_continuity_summary": dict(continuity_summary),
        "contradiction_staleness_summary": dict(contradiction_summary),
        "campaign_throughput_bottleneck_summary": dict(throughput_summary),
        "experiment_dedup_novelty_summary": dict(novelty_summary),
        "memory_artifacts": {
            "package_memory_path": str(package_status.get("path") or "logs/qre_research_memory/latest.json"),
            "coverage_path": "logs/qre_research_memory_coverage/latest.json",
            "failure_retrieval_path": "logs/qre_failure_retrieval/latest.json",
            "artifact_continuity_path": "logs/qre_read_only_artifact_continuity/latest.json",
            "contradiction_staleness_path": "logs/qre_contradiction_staleness_intelligence/latest.json",
            "campaign_throughput_bottleneck_path": "logs/qre_campaign_throughput_bottleneck_intelligence/latest.json",
            "experiment_dedup_novelty_path": "logs/qre_experiment_dedup_novelty_enforcement/latest.json",
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
    summary = report.get("summary") or {}
    artifacts = report.get("memory_artifacts") if isinstance(report.get("memory_artifacts"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Research Memory Current Artifacts",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 1. Current Status",
            _table(
                ["Field", "Value"],
                [
                    ["package_research_memory_status", str(summary.get("package_research_memory_status") or "")],
                    ["package_research_memory_ready", str(summary.get("package_research_memory_ready") or False)],
                    ["coverage_ready", str(summary.get("coverage_ready") or False)],
                    ["retrieval_ready", str(summary.get("retrieval_ready") or False)],
                    ["artifact_continuity_ready", str(summary.get("artifact_continuity_ready") or False)],
                    ["contradiction_staleness_ready", str(summary.get("contradiction_staleness_ready") or False)],
                    ["campaign_throughput_bottleneck_intelligence_ready", str(summary.get("campaign_throughput_bottleneck_intelligence_ready") or False)],
                    ["experiment_dedup_novelty_enforcement_ready", str(summary.get("experiment_dedup_novelty_enforcement_ready") or False)],
                    ["indexed_entry_count", str(summary.get("indexed_entry_count") or 0)],
                    ["retrievable_failure_subject_count", str(summary.get("retrievable_failure_subject_count") or 0)],
                    ["artifact_continuity_materializable_target_count", str(summary.get("artifact_continuity_materializable_target_count") or 0)],
                    ["visible_contradiction_count", str(summary.get("visible_contradiction_count") or 0)],
                    ["visible_stale_or_superseded_count", str(summary.get("visible_stale_or_superseded_count") or 0)],
                    ["visible_campaign_throughput_bottleneck_count", str(summary.get("visible_campaign_throughput_bottleneck_count") or 0)],
                    ["visible_experiment_duplicate_pressure_count", str(summary.get("visible_experiment_duplicate_pressure_count") or 0)],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            "## 2. Artifact Paths",
            _table(
                ["Artifact", "Path"],
                [
                    ["package_memory_path", str(artifacts.get("package_memory_path") or "")],
                    ["coverage_path", str(artifacts.get("coverage_path") or "")],
                    ["failure_retrieval_path", str(artifacts.get("failure_retrieval_path") or "")],
                    ["artifact_continuity_path", str(artifacts.get("artifact_continuity_path") or "")],
                    ["contradiction_staleness_path", str(artifacts.get("contradiction_staleness_path") or "")],
                    ["campaign_throughput_bottleneck_path", str(artifacts.get("campaign_throughput_bottleneck_path") or "")],
                    ["experiment_dedup_novelty_path", str(artifacts.get("experiment_dedup_novelty_path") or "")],
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_research_memory_current_artifacts: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, str]:
    memory = memory_coverage.build_research_memory_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    retrieval = memory_coverage.build_failure_retrieval(memory)
    memory_paths = memory_coverage.write_outputs(memory, retrieval, repo_root=repo_root)
    continuity_report = artifact_continuity.build_read_only_artifact_continuity(repo_root=repo_root)
    continuity_paths = artifact_continuity.write_outputs(continuity_report, repo_root=repo_root)
    contradiction_report = contradiction_staleness.build_contradiction_staleness_intelligence(repo_root=repo_root)
    contradiction_paths = contradiction_staleness.write_outputs(contradiction_report, repo_root=repo_root)
    throughput_report = throughput_bottlenecks.build_campaign_throughput_bottleneck_intelligence(repo_root=repo_root)
    throughput_paths = throughput_bottlenecks.write_outputs(throughput_report, repo_root=repo_root)
    novelty_report = novelty_enforcement.build_experiment_dedup_novelty_enforcement(repo_root=repo_root)
    novelty_paths = novelty_enforcement.write_outputs(novelty_report, repo_root=repo_root)

    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        **memory_paths,
        "artifact_continuity_latest": continuity_paths["latest"],
        "artifact_continuity_operator_summary": continuity_paths["operator_summary"],
        "contradiction_staleness_latest": contradiction_paths["latest"],
        "contradiction_staleness_operator_summary": contradiction_paths["operator_summary"],
        "campaign_throughput_bottleneck_latest": throughput_paths["latest"],
        "campaign_throughput_bottleneck_operator_summary": throughput_paths["operator_summary"],
        "experiment_dedup_novelty_latest": novelty_paths["latest"],
        "experiment_dedup_novelty_operator_summary": novelty_paths["operator_summary"],
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_research_memory_current_artifacts",
        description="Materialize current research-memory coverage and retrieval artifacts.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_research_memory_current_artifacts(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report, max_candidates=args.max_candidates)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
