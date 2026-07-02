from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.qre_research import autonomous_opportunity_loop as aol


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_repeated_invocation_uses_same_external_watermark(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "cache_roots": [{"cache_kind": "ohlcv", "status": "ready"}],
            "coverage": [
                {
                    "source": "polygon",
                    "instrument": "AAPL",
                    "timeframe": "4h",
                    "content_hash": "hash-a",
                    "max_timestamp_utc": "2026-06-30T20:00:00Z",
                }
            ],
        },
    )
    _write_json(
        repo_root / "logs/qre_data_source_quality_readiness/latest.json",
        {"sources": [{"source": "polygon", "ready": "READY"}]},
    )
    _write_json(
        repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        {"rows": []},
    )
    _write_json(
        repo_root / "generated_research/primitives/registry/generated_primitive_registry.v1.json",
        {"rows": []},
    )
    _write_json(
        repo_root / "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
        {"rows": []},
    )
    _write_json(
        repo_root / "generated_research/hypotheses/lifecycle/research_memory.v1.json",
        {"rows": []},
    )
    _write_json(
        repo_root / "generated_research/hypotheses/lifecycle/evidence_updates.v1.json",
        {"rows": []},
    )
    _write_json(
        repo_root / "generated_research/orchestration/trust_closure/research_continuation_plan.v1.json",
        {"required_novelty": ["NEW_COMPLETE_MARKET_DATA"], "blocked_cells": []},
    )
    monkeypatch.setattr(aol.a20, "build_evidence_snapshot", lambda *, repo_root=None: {"manual_thesis_digest": "manual-digest"})
    monkeypatch.setattr(aol.qhl, "run_trusted_hypothesis_loop", lambda *, repo_root=None, write_outputs=True: {"summary": {}})
    monkeypatch.setattr(aol, "_write_ade_bridge_artifacts", lambda **kwargs: {"promotion_snapshot": None, "admission_snapshot": None})

    first = aol.run_opportunity_loop(repo_root=repo_root, write_outputs=True)
    second = aol.run_opportunity_loop(repo_root=repo_root, write_outputs=True)
    third = aol.run_opportunity_loop(repo_root=repo_root, write_outputs=True)

    assert first["watermark"]["watermark_id"] == second["watermark"]["watermark_id"] == third["watermark"]["watermark_id"]
    assert second["precheck"]["precheck_status"] == "NO_MATERIAL_CHANGE"
    assert third["precheck"]["precheck_status"] == "NO_MATERIAL_CHANGE"
    assert second["ade_requests"]["new_requests"] == 0
    assert third["ade_requests"]["new_requests"] == 0
