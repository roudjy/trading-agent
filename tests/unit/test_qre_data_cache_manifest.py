from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from packages.qre_data import cache_manifest as manifest


def _write_parquet(path: Path, timestamps: list[datetime]) -> None:
    table = pa.table(
        {
            "instrument_id": ["btc-usd"] * len(timestamps),
            "interval": ["1h"] * len(timestamps),
            "timestamp_utc": timestamps,
            "close": [100.0 + i for i, _ in enumerate(timestamps)],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def test_build_cache_manifest_reports_file_and_coverage_rows(tmp_path: Path) -> None:
    cache = tmp_path / "data" / "cache" / "market"
    _write_parquet(
        cache / "yfinance__BTC-USD__1h__20260401__20260403__abc123.parquet",
        [
            datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 4, 1, 1, 0, tzinfo=UTC),
            datetime(2026, 4, 1, 2, 0, tzinfo=UTC),
        ],
    )

    payload = manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert payload["schema_version"] == "1.0"
    assert payload["summary"]["research_ready"] is True
    assert payload["summary"]["cache_file_count"] == 1
    assert payload["summary"]["total_rows"] == 3
    assert payload["files"][0]["source"] == "yfinance"
    assert payload["files"][0]["instrument"] == "BTC-USD"
    assert payload["files"][0]["timeframe"] == "1h"
    assert payload["files"][0]["row_count"] == 3
    assert payload["files"][0]["min_timestamp_utc"] == "2026-04-01T00:00:00Z"
    assert payload["files"][0]["max_timestamp_utc"] == "2026-04-01T02:00:00Z"
    assert payload["files"][0]["content_hash"].startswith("sha256:")
    assert payload["coverage"] == [
        {
            "source": "yfinance",
            "instrument": "BTC-USD",
            "timeframe": "1h",
            "file_count": 1,
            "row_count": 3,
            "min_timestamp_utc": "2026-04-01T00:00:00Z",
            "max_timestamp_utc": "2026-04-01T02:00:00Z",
            "content_hash": payload["coverage"][0]["content_hash"],
            "status_counts": {"ready": 1},
            "ready": True,
        }
    ]


def test_missing_cache_root_fails_closed(tmp_path: Path) -> None:
    payload = manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert payload["summary"]["research_ready"] is False
    assert payload["summary"]["status"] == "not_ready"
    assert payload["summary"]["missing_roots"] == 1
    assert payload["cache_roots"] == [
        {
            "cache_kind": "market",
            "path": "data/cache/market",
            "status": "missing",
        }
    ]
    assert payload["files"] == []
    assert payload["coverage"] == []


def test_manifest_output_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    cache = tmp_path / "data" / "cache" / "market"
    _write_parquet(
        cache / "yfinance__ETH-USD__4h__20260401__20260402__def456.parquet",
        [datetime(2026, 4, 1, 0, 0, tzinfo=UTC)],
    )

    left = manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )
    right = manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert left == right


def test_read_manifest_status_fails_closed_until_manifest_exists(tmp_path: Path) -> None:
    missing = manifest.read_manifest_status(
        output_dir=Path("logs/qre_data_cache_manifest"),
        repo_root=tmp_path,
    )

    assert missing == {
        "status": "missing_manifest",
        "research_ready": False,
        "path": "logs/qre_data_cache_manifest/latest.json",
        "fails_closed": True,
    }

    cache = tmp_path / "data" / "cache" / "market"
    _write_parquet(
        cache / "yfinance__AAPL__1d__20260401__20260402__ghi789.parquet",
        [datetime(2026, 4, 1, 0, 0, tzinfo=UTC)],
    )
    payload = manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )
    manifest.write_manifest_outputs(
        payload,
        output_dir=Path("logs/qre_data_cache_manifest"),
        repo_root=tmp_path,
    )

    present = manifest.read_manifest_status(
        output_dir=Path("logs/qre_data_cache_manifest"),
        repo_root=tmp_path,
    )

    assert present == {
        "status": "ready",
        "research_ready": True,
        "path": "logs/qre_data_cache_manifest/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_safety_invariants_keep_manifest_read_only(tmp_path: Path) -> None:
    payload = manifest.build_cache_manifest(repo_root=tmp_path)

    assert payload["safe_to_execute"] is False
    assert payload["safety_invariants"] == {
        "read_only": True,
        "fetches_external_data": False,
        "mutates_cache": False,
        "mutates_research_outputs": False,
        "frozen_contracts_unchanged": True,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
    }
