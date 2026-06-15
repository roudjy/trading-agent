from __future__ import annotations

import json
from pathlib import Path

from research import qre_cache_throughput_manifest as throughput


FROZEN = "2026-05-23T00:00:00Z"


def _cache_manifest(*, ready: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_data_cache_manifest",
        "generated_at_utc": FROZEN,
        "summary": {
            "status": "ready" if ready else "not_ready",
            "research_ready": ready,
            "cache_file_count": 1,
            "coverage_row_count": 1,
            "total_rows": 3,
            "source_count": 1,
            "instrument_count": 1,
            "timeframe_count": 1,
            "status_counts": {"ready": 1},
            "missing_roots": 0,
            "manifest_content_hash": "sha256:abc123",
            "missing_manifest_fails_closed": True,
        },
        "cache_roots": [
            {
                "cache_kind": "market",
                "path": "data/cache/market",
                "status": "present",
            }
        ],
        "files": [
            {
                "path": "data/cache/market/yfinance__BTC-USD__1h__20260401__20260403__abc123.parquet",
                "cache_kind": "market",
                "source": "yfinance",
                "instrument": "BTC-USD",
                "timeframe": "1h",
                "requested_start": "2026-04-01",
                "requested_end": "2026-04-03",
                "cache_key": "abc123",
                "status": "ready",
                "row_count": 3,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": "2026-04-01T02:00:00Z",
                "size_bytes": 123,
                "content_hash": "sha256:def456",
            }
        ],
        "coverage": [
            {
                "source": "yfinance",
                "instrument": "BTC-USD",
                "timeframe": "1h",
                "file_count": 1,
                "row_count": 3,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": "2026-04-01T02:00:00Z",
                "content_hash": "sha256:def456",
                "status_counts": {"ready": 1},
                "ready": True,
            }
        ],
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "frozen_contracts_unchanged": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def test_build_cache_throughput_manifest_reports_read_only_policies(tmp_path: Path) -> None:
    manifest_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")

    report = throughput.build_cache_throughput_manifest(
        repo_root=tmp_path,
        cache_manifest_path=Path("logs/qre_data_cache_manifest/latest.json"),
        generated_at_utc=FROZEN,
        duckdb_available=True,
        polars_available=True,
    )

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_cache_throughput_manifest"
    assert report["summary"]["research_ready"] is True
    assert report["summary"]["cache_manifest_ready"] is True
    assert report["summary"]["snapshot_contract_ready"] is True
    assert report["summary"]["duckdb_catalog_manifest_ready"] is True
    assert report["summary"]["polars_use_policy_ready"] is True
    assert report["summary"]["blocked_reason_counts"] == {}
    assert report["cache_manifest_reference"]["manifest_content_hash"] == "sha256:abc123"
    assert report["snapshot_contract"]["file_format"] == "parquet"
    assert report["snapshot_contract"]["parquet_only"] is True
    assert report["snapshot_contract"]["ready"] is True
    assert report["duckdb_catalog_manifest"]["module_available"] is True
    assert report["duckdb_catalog_manifest"]["ready"] is True
    assert report["polars_use_policy"]["module_available"] is True
    assert report["polars_use_policy"]["allowed_for_local_read_only_scans"] is True
    assert report["throughput_blockers"] == []


def test_missing_cache_manifest_fails_closed(tmp_path: Path) -> None:
    report = throughput.build_cache_throughput_manifest(
        repo_root=tmp_path,
        cache_manifest_path=Path("logs/qre_data_cache_manifest/latest.json"),
        generated_at_utc=FROZEN,
        duckdb_available=False,
        polars_available=False,
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["status"] == "not_ready"
    assert report["summary"]["cache_manifest_ready"] is False
    assert report["summary"]["snapshot_contract_ready"] is False
    assert report["summary"]["duckdb_catalog_manifest_ready"] is False
    assert report["summary"]["polars_use_policy_ready"] is False
    assert report["summary"]["blocked_reason_counts"] == {
        "cache_manifest_not_research_ready": 1,
        "duckdb_module_unavailable": 1,
        "parquet_snapshot_contract_not_ready": 1,
        "polars_module_unavailable": 1,
    }
    assert report["snapshot_contract"]["ready"] is False
    assert report["duckdb_catalog_manifest"]["ready"] is False
    assert report["polars_use_policy"]["ready"] is False
    assert report["throughput_blockers"][0]["fail_closed"] is True


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    report = throughput.build_cache_throughput_manifest(
        repo_root=tmp_path,
        cache_manifest_path=Path("logs/qre_data_cache_manifest/latest.json"),
        generated_at_utc=FROZEN,
        duckdb_available=True,
        polars_available=True,
    )

    paths = throughput.write_outputs(
        report,
        repo_root=tmp_path,
        output_dir=Path("logs/qre_cache_throughput_manifest"),
    )

    assert paths == {
        "latest": "logs/qre_cache_throughput_manifest/latest.json",
        "timestamped": "logs/qre_cache_throughput_manifest/2026-05-23T00-00-00Z.json",
        "history": "logs/qre_cache_throughput_manifest/history.jsonl",
        "operator_summary": "logs/qre_cache_throughput_manifest/operator_summary.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
    assert throughput.read_throughput_status(
        repo_root=tmp_path,
        output_dir=Path("logs/qre_cache_throughput_manifest"),
    ) == {
        "status": "ready",
        "research_ready": True,
        "path": "logs/qre_cache_throughput_manifest/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_safety_invariants_keep_report_read_only(tmp_path: Path) -> None:
    manifest_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")

    report = throughput.build_cache_throughput_manifest(
        repo_root=tmp_path,
        cache_manifest_path=Path("logs/qre_data_cache_manifest/latest.json"),
        generated_at_utc=FROZEN,
        duckdb_available=True,
        polars_available=False,
    )

    assert report["safe_to_execute"] is False
    assert report["safety_invariants"] == {
        "read_only": True,
        "fetches_external_data": False,
        "mutates_cache": False,
        "mutates_research_outputs": False,
        "frozen_contracts_unchanged": True,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
        "throughput_cannot_bypass_source_quality": True,
        "duckdb_catalog_is_manifest_only": True,
        "polars_use_is_read_only_scan_only": True,
    }
