from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from packages.qre_research.alpha_discovery import runner as adr
from packages.qre_research.alpha_discovery.contracts import (
    ObservationSnapshot,
    content_id,
)
from reporting import qre_research_operations as ops


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _snapshot() -> ObservationSnapshot:
    fields = {
        "market_diagnostics": {"status": "READY"},
        "regime_diagnostics": {"regime_signature": ["trend", "calm"]},
        "cross_asset_diagnostics": {"status": "NOT_AVAILABLE"},
        "data_coverage": {"coverage_rows": 1, "ready_rows": 1, "research_ready": True},
        "source_quality": {"summary": {"status": "ready"}, "sources": []},
        "identity_readiness": "ready",
        "current_queue": [],
        "recent_terminal_outcomes": [],
        "active_contradictions": [],
        "resolved_contradictions": [],
        "mechanism_coverage": {"opportunity_count": 1},
        "behavior_family_coverage": {"resolved_strategy_count": 1},
        "primitive_inventory": {"available_primitives": ["compression_ratio"]},
        "executor_inventory": {"canonical_engine": "canonical"},
        "relevant_research_memory": {"summary": {"memory_content_hash": "fixture"}, "matches": []},
    }
    payload = dict(fields)
    payload["content_identity"] = content_id("qos", payload)
    return ObservationSnapshot(
        observation_snapshot_id=content_id("qos", payload),
        schema_version="1.0",
        policy_version="qre_alpha_discovery_mvp_v2",
        **payload,
    )


def _prepare_repo(repo_root: Path) -> None:
    cache_path = repo_root / "data/cache/market/yfinance__AAPL__1d__20260408__20260415__abc.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2026-04-08", periods=5, freq="D", tz="UTC"),
            "open": [1.0, 1.1, 1.2, 1.3, 1.4],
            "high": [1.1, 1.2, 1.3, 1.4, 1.5],
            "low": [0.9, 1.0, 1.1, 1.2, 1.3],
            "close": [1.05, 1.15, 1.25, 1.35, 1.45],
            "volume": [100, 110, 120, 130, 140],
        }
    ).to_parquet(cache_path, index=False)
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_data_cache_manifest",
            "summary": {"research_ready": False},
            "files": [
                {
                    "path": cache_path.relative_to(repo_root).as_posix(),
                    "cache_kind": "market",
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "status": "ready",
                    "row_count": 5,
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "max_timestamp_utc": "2026-04-12T00:00:00Z",
                    "content_hash": "sha256:test",
                }
            ],
            "coverage": [
                {
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "status": "ready",
                    "row_count": 5,
                    "content_hash": "sha256:test",
                }
            ],
        },
    )
    _write_json(repo_root / "logs/qre_data_source_quality_readiness/latest.json", {"schema_version": "1.0", "rows": []})


def test_cli_run_uses_lesson_to_suppress_repeated_campaign(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "repo"
    _prepare_repo(repo_root)
    monkeypatch.setattr(adr, "build_observation_snapshot", lambda context: _snapshot())
    monkeypatch.setattr(adr, "validate_write_target", lambda path: None)

    first_rc = ops.main(["--repo-root", str(repo_root), "alpha-discovery-run-once", "--max-hypotheses", "3"])
    first_payload = json.loads(capsys.readouterr().out)
    assert first_rc == 0
    assert first_payload["data_plan_status"] == "CACHE_READY"
    assert first_payload["campaign_id"]
    assert first_payload["lesson_id"]

    second_rc = ops.main(["--repo-root", str(repo_root), "alpha-discovery-run-once", "--max-hypotheses", "3"])
    second_payload = json.loads(capsys.readouterr().out)
    assert second_rc == 0
    assert second_payload["data_plan_status"] == "CACHE_READY"
    assert second_payload["selected_hypothesis"]["stable_fingerprint"] != first_payload["selected_hypothesis"]["stable_fingerprint"]
    assert any(
        item.get("reason") == "suppressed_by_recent_lesson"
        for item in second_payload["unselected_hypothesis_reasons"]
    )
    assert second_payload["campaign_id"] != first_payload["campaign_id"]
    assert second_payload["terminal_disposition"] == "NEEDS_MORE_EVIDENCE"
