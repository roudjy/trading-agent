from __future__ import annotations

import ast
import json
from pathlib import Path

from packages.qre_research import research_memory


def _write_research_latest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": "2026-05-23T00:00:00Z",
        "count": 2,
        "summary": {"success": 1, "failed": 1, "goedgekeurd": 0},
        "results": [
            {
                "strategy_name": "trend_following",
                "family": "trend",
                "hypothesis": "Trend continuation survives high-volume regimes",
                "asset": "BTC-USD",
                "interval": "1h",
                "success": True,
                "error": "",
            },
            {
                "strategy_name": "screening_candidate",
                "family": "screening",
                "hypothesis": "Breakout filter improves candidate quality",
                "asset": "ETH-USD",
                "interval": "4h",
                "success": False,
                "error": "unknown_screening_failure",
            },
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_queue_doc(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# ADE Queue",
                "- queue id: `ADE-QRE-005`",
                "- status: `ready`",
                "- scope: deterministic artifact index and related-failure lookup",
                "- governance policy: read-only local evidence only",
                "- verboden scope: routing mutation and strategy generation",
            ]
        ),
        encoding="utf-8",
    )


def test_build_research_memory_indexes_hypotheses_failures_and_policy(tmp_path: Path) -> None:
    latest = tmp_path / "research" / "research_latest.json"
    queue_doc = tmp_path / "docs" / "governance" / "ade_queue.md"
    _write_research_latest(latest)
    _write_queue_doc(queue_doc)

    memory = research_memory.build_research_memory(
        artifact_paths=[
            Path("research/research_latest.json"),
            Path("docs/governance/ade_queue.md"),
        ],
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert memory["schema_version"] == "1.0"
    assert memory["summary"]["research_memory_ready"] is True
    assert memory["summary"]["artifact_count"] == 2
    assert memory["summary"]["entry_count"] == 3
    assert memory["summary"]["ontology_tag_counts"]["hypothesis"] == 2
    assert memory["summary"]["ontology_tag_counts"]["failure"] >= 1
    assert memory["summary"]["ontology_tag_counts"]["policy"] >= 1
    assert memory["missing_artifacts"] == []


def test_retrieval_is_deterministic_and_metadata_backed(tmp_path: Path) -> None:
    latest = tmp_path / "research" / "research_latest.json"
    _write_research_latest(latest)
    left = research_memory.build_research_memory(
        artifact_paths=[Path("research/research_latest.json")],
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
        query="breakout unknown_screening_failure",
    )
    right = research_memory.build_research_memory(
        artifact_paths=[Path("research/research_latest.json")],
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
        query="breakout unknown_screening_failure",
    )

    assert left == right
    match = left["retrieval"]["matches"][0]
    assert match["artifact_id"] == "research/research_latest.json#results[1]"
    assert match["record_kind"] == "research_result"
    assert "failure" in match["ontology_tags"]


def test_related_failure_lookup_filters_to_failure_evidence(tmp_path: Path) -> None:
    latest = tmp_path / "research" / "research_latest.json"
    _write_research_latest(latest)

    memory = research_memory.build_research_memory(
        artifact_paths=[Path("research/research_latest.json")],
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
        related_failure="unknown_screening_failure",
    )

    assert memory["related_failures"]["matches"]
    assert memory["related_failures"]["matches"][0]["artifact_id"].endswith("results[1]")


def test_research_memory_fails_closed_without_entries(tmp_path: Path) -> None:
    memory = research_memory.build_research_memory(
        artifact_paths=[Path("missing.json")],
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert memory["summary"]["status"] == "not_ready"
    assert memory["summary"]["research_memory_ready"] is False
    assert memory["summary"]["fail_closed"] is True
    assert memory["missing_artifacts"] == ["missing.json"]


def test_read_research_memory_status_fails_closed_until_sidecar_exists(tmp_path: Path) -> None:
    missing = research_memory.read_research_memory_status(
        output_dir=Path("logs/qre_research_memory"),
        repo_root=tmp_path,
    )

    assert missing == {
        "status": "missing_research_memory",
        "research_memory_ready": False,
        "path": "logs/qre_research_memory/latest.json",
        "fails_closed": True,
    }

    latest = tmp_path / "research" / "research_latest.json"
    _write_research_latest(latest)
    memory = research_memory.build_research_memory(
        artifact_paths=[Path("research/research_latest.json")],
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )
    research_memory.write_research_memory_outputs(
        memory,
        output_dir=Path("logs/qre_research_memory"),
        repo_root=tmp_path,
    )

    assert research_memory.read_research_memory_status(
        output_dir=Path("logs/qre_research_memory"),
        repo_root=tmp_path,
    ) == {
        "status": "ready",
        "research_memory_ready": True,
        "path": "logs/qre_research_memory/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_research_memory_source_avoids_network_and_subprocess_imports() -> None:
    source = Path(research_memory.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "requests." not in source


def test_safety_invariants_keep_research_memory_read_only(tmp_path: Path) -> None:
    memory = research_memory.build_research_memory(
        artifact_paths=[Path("missing.json")],
        repo_root=tmp_path,
    )

    assert memory["safe_to_execute"] is False
    assert memory["safety_invariants"] == {
        "read_only": True,
        "uses_local_artifacts_only": True,
        "uses_embeddings": False,
        "uses_llm_authority": False,
        "uses_network": False,
        "uses_subprocess": False,
        "mutates_campaigns": False,
        "mutates_research_outputs": False,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
    }
