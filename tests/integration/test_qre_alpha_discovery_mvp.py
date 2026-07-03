from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from packages.qre_research.alpha_discovery import runner as adr
from packages.qre_research.alpha_discovery.contracts import ObservationSnapshot, content_id
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
        schema_version="1.1",
        policy_version="qre_alpha_discovery_followup_pr2_v1",
        **payload,
    )


def _prepare_repo(repo_root: Path) -> None:
    cache_dir = repo_root / "data/cache/market"
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    files = []
    for index in range(3):
        start = pd.Timestamp("2026-04-08", tz="UTC") + pd.Timedelta(days=index * 40)
        timestamps = pd.date_range(start, periods=40, freq="D", tz="UTC")
        offsets = [int((ts - pd.Timestamp("2026-04-08", tz="UTC")).days) for ts in timestamps]
        frame = pd.DataFrame(
            {
                "timestamp_utc": timestamps,
                "open": [1.0 + i for i in offsets],
                "high": [1.1 + i for i in offsets],
                "low": [0.9 + i for i in offsets],
                "close": [1.05 + i for i in offsets],
                "volume": [100 + i for i in offsets],
            }
        )
        path = cache_dir / f"yfinance__BTC-USD__1d__2026040{index+8}__2026041{index+5}__fixture{index}.parquet"
        frame.to_parquet(path, index=False)
        frames.append(frame)
        files.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "cache_kind": "market",
                "source": "yfinance",
                "instrument": "BTC-USD",
                "timeframe": "1d",
                "status": "ready",
                "row_count": 40,
                "min_timestamp_utc": frame["timestamp_utc"].iloc[0].isoformat().replace("+00:00", "Z"),
                "max_timestamp_utc": frame["timestamp_utc"].iloc[-1].isoformat().replace("+00:00", "Z"),
                "content_hash": f"sha256:test{index}",
                "identity_status": "ready",
            }
        )
    combined = pd.concat(frames, ignore_index=True)
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_data_cache_manifest",
            "summary": {"research_ready": True},
            "files": files,
            "coverage": [
                {
                    "source": "yfinance",
                    "instrument": "BTC-USD",
                    "timeframe": "1d",
                    "file_count": 3,
                    "row_count": len(combined),
                    "min_timestamp_utc": combined["timestamp_utc"].iloc[0].isoformat().replace("+00:00", "Z"),
                    "max_timestamp_utc": combined["timestamp_utc"].iloc[-1].isoformat().replace("+00:00", "Z"),
                    "content_hash": "sha256:logical",
                    "status_counts": {"ready": 3},
                    "ready": True,
                }
            ],
        },
    )
    _write_json(
        repo_root / "logs/qre_data_source_quality_readiness/latest.json",
        {
            "schema_version": "1.0",
            "summary": {"status": "ready", "identity_status": "ready"},
            "rows": [
                {
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "effective_research_quality_status": "ready",
                    "source_quality_status": "ready",
                    "identity_status": "ready",
                }
            ],
        },
    )


def test_cli_auto_run_stops_at_source_quality_boundary_and_preserves_no_empirical_campaign(tmp_path: Path, monkeypatch, capsys) -> None:
    repo_root = tmp_path / "repo"
    _prepare_repo(repo_root)
    monkeypatch.setattr(adr, "build_observation_snapshot", lambda context: _snapshot())
    monkeypatch.setattr(adr, "validate_write_target", lambda path: None)

    rc = ops.main(["--repo-root", str(repo_root), "alpha-discovery-run-once", "--max-hypotheses", "3", "--execution-tier", "auto"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["admitted_execution_tier"] == "EXECUTOR_SMOKE"
    assert payload["empirical_campaign_created"] is False
    assert payload["smoke_execution_created"] is False
    assert payload["terminal_disposition"] == "STOPPED_SOURCE_CERTIFICATION_BOUNDARY"
    assert payload["five_row_inventory_root_cause"]["selector_effect"] == "physical shard rows with 5 bars each were treated as standalone datasets"
