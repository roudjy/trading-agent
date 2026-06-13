from __future__ import annotations

import json
from pathlib import Path

from research.qre_build_request_writer import build_request_packet, write_build_request
from research.qre_next_action_classifier import classify_next_action


def _cycle() -> dict:
    return {
        "cycle_id": "cycle-1",
        "source_research_run_id": "research-run-2",
        "source_research_run_group_id": "research-group",
        "next_market_intake_seed": {
            "seed_id": "seed-1",
            "statement": "keep same universe",
        },
        "result_analysis": {
            "content_blockers": ["safe_metric_runner_missing_or_cache_unavailable"]
        },
    }


def test_build_request_packet_is_artifact_only_and_actionable() -> None:
    packet = build_request_packet(
        source_cycle=_cycle(),
        classification=classify_next_action("add_cache_only_metric_path"),
        created_at_utc="2026-06-13T00:00:00Z",
    )

    assert packet["request_id"].startswith("build-request-")
    assert packet["safe_for_ade_build"] is True
    assert packet["execution_allowed"] is False
    assert packet["build_executed_by_this_controller"] is False
    assert packet["recommended_branch"] == "feat/qre-add-cache-only-metric-path"
    assert "public_research_output_mutation" in packet["forbidden_actions"]
    assert packet["post_merge_research_command"] == (
        "python -m research.qre_autonomous_market_research_loop --write --max-cycles 3"
    )


def test_write_build_request_writes_required_files(tmp_path: Path) -> None:
    packet = build_request_packet(
        source_cycle=_cycle(),
        classification=classify_next_action("add_cache_only_metric_path"),
        created_at_utc="2026-06-13T00:00:00Z",
    )

    paths = write_build_request(packet, output_dir=tmp_path)

    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert Path(paths["latest"]).name == "latest_build_request.json"
    parsed = json.loads(Path(paths["latest"]).read_text(encoding="utf-8"))
    assert parsed["request_id"] == packet["request_id"]
    assert "QRE Build Request" in Path(paths["markdown"]).read_text(encoding="utf-8")


def test_existing_build_request_is_not_recreated_when_overwrite_false(tmp_path: Path) -> None:
    packet = build_request_packet(
        source_cycle=_cycle(),
        classification=classify_next_action("add_cache_only_metric_path"),
        created_at_utc="2026-06-13T00:00:00Z",
    )

    first = write_build_request(packet, output_dir=tmp_path, overwrite=False)
    second = write_build_request(packet, output_dir=tmp_path, overwrite=False)

    assert first["created"] is True
    assert second["created"] is False

