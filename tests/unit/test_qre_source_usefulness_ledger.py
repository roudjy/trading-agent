from __future__ import annotations

import json
from pathlib import Path

from research import qre_source_usefulness_ledger as ledger


FROZEN = "2026-05-23T00:00:00Z"


def _cache_manifest(*, ready: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_data_cache_manifest",
        "generated_at_utc": FROZEN,
        "summary": {
            "status": "ready" if ready else "not_ready",
            "research_ready": ready,
            "cache_file_count": 2,
            "coverage_row_count": 2,
            "total_rows": 5,
            "source_count": 2,
            "instrument_count": 2,
            "timeframe_count": 2,
            "status_counts": {"ready": 1, "missing_timestamp": 1},
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
            },
            {
                "path": "data/cache/market/coinbase__ETH-USD__1h__20260401__20260403__def456.parquet",
                "cache_kind": "market",
                "source": "coinbase",
                "instrument": "ETH-USD",
                "timeframe": "1h",
                "requested_start": "2026-04-01",
                "requested_end": "2026-04-03",
                "cache_key": "def456",
                "status": "missing_timestamp",
                "row_count": 2,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": None,
                "size_bytes": 111,
                "content_hash": "sha256:ghi789",
            },
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
            },
            {
                "source": "coinbase",
                "instrument": "ETH-USD",
                "timeframe": "1h",
                "file_count": 1,
                "row_count": 2,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": None,
                "content_hash": "sha256:ghi789",
                "status_counts": {"missing_timestamp": 1},
                "ready": False,
            },
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


def _source_quality(*, ready: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_data_source_quality_readiness",
        "generated_at_utc": FROZEN,
        "summary": {
            "status": "ready" if ready else "not_ready",
            "research_ready": ready,
            "source_quality_ready": ready,
            "manifest_research_ready": ready,
            "fail_closed": not ready,
            "file_count": 2,
            "source_count": 2,
            "identity_confidence_counts": {"high": 2},
            "quality_status_counts": {"blocked": 1, "ready": 1},
            "blocking_reason_counts": {"identity_not_high_confidence": 1},
            "readiness_blocker_category_counts": {"source": 1},
            "readiness_blocker_reason_counts": {"source_manifest_status_not_ready": 1},
            "report_readiness_blockers": [],
            "evidence_content_hash": "sha256:sourcehash",
            "operator_summary": "source-quality summary",
        },
        "sources": [
            {
                "source": "yfinance",
                "file_count": 1,
                "identity_confidence_counts": {"high": 1},
                "quality_status_counts": {"ready": 1},
                "blocking_reason_counts": {},
                "readiness_blocker_category_counts": {},
                "readiness_blocker_reason_counts": {},
                "ready": True,
            },
            {
                "source": "coinbase",
                "file_count": 1,
                "identity_confidence_counts": {"high": 1},
                "quality_status_counts": {"blocked": 1},
                "blocking_reason_counts": {"manifest_status_missing_timestamp": 1},
                "readiness_blocker_category_counts": {"source": 1},
                "readiness_blocker_reason_counts": {"source_manifest_status_not_ready": 1},
                "ready": False,
            },
        ],
        "rows": [
            {
                "path": "data/cache/market/yfinance__BTC-USD__1h__20260401__20260403__abc123.parquet",
                "cache_kind": "market",
                "source": "yfinance",
                "instrument": "BTC-USD",
                "timeframe": "1h",
                "identity_confidence": "high",
                "quality_status": "ready",
                "blocking_reasons": [],
                "readiness_blockers": [],
                "manifest_status": "ready",
                "row_count": 3,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": "2026-04-01T02:00:00Z",
                "content_hash": "sha256:def456",
                "operator_explanation": "ready",
            },
            {
                "path": "data/cache/market/coinbase__ETH-USD__1h__20260401__20260403__def456.parquet",
                "cache_kind": "market",
                "source": "coinbase",
                "instrument": "ETH-USD",
                "timeframe": "1h",
                "identity_confidence": "high",
                "quality_status": "blocked",
                "blocking_reasons": ["manifest_status_missing_timestamp"],
                "readiness_blockers": [
                    {
                        "category": "source",
                        "reason": "source_manifest_status_not_ready",
                        "evidence_field": "status",
                        "evidence_status": "missing_timestamp",
                        "fail_closed": True,
                        "operator_explanation": "blocked",
                    }
                ],
                "manifest_status": "missing_timestamp",
                "row_count": 2,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": None,
                "content_hash": "sha256:ghi789",
                "operator_explanation": "blocked",
            },
        ],
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "activates_vendor_sources": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "frozen_contracts_unchanged": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "addendum3_reference_taxonomy_only": True,
            "activates_addendum3_runtime": False,
            "source_quality_as_alpha": False,
            "source_quality_as_promotion_authority": False,
        },
    }


def test_build_source_usefulness_ledger_aggregates_proxy_metrics(tmp_path: Path) -> None:
    cache_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    source_path = tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    source_path.write_text(json.dumps(_source_quality()), encoding="utf-8")

    report = ledger.build_source_usefulness_ledger(repo_root=tmp_path)

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_source_usefulness_ledger"
    assert report["summary"]["research_ready"] is True
    assert report["summary"]["cache_manifest_ready"] is True
    assert report["summary"]["source_quality_ready"] is True
    assert report["summary"]["source_count"] == 2
    assert report["summary"]["ready_source_count"] == 1
    assert report["summary"]["blocked_source_count"] == 1
    assert report["summary"]["cache_hit_proxy_rows"] == 1
    assert report["summary"]["quality_failure_rows"] == 1
    assert report["summary"]["false_positive_proxy_rows"] == 1
    assert report["summary"]["cache_hit_ratio"] == 0.6
    assert report["rows"][0]["source"] == "coinbase"
    assert report["rows"][0]["usefulness_state"] == "blocked"
    assert report["rows"][1]["source"] == "yfinance"
    assert report["rows"][1]["usefulness_state"] == "useful"
    assert report["blockers"] == []


def test_missing_sidecars_fail_closed(tmp_path: Path) -> None:
    report = ledger.build_source_usefulness_ledger(repo_root=tmp_path)

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["status"] == "not_ready"
    assert report["summary"]["blocking_reasons"] == [
        "cache_manifest_missing",
        "source_quality_missing",
        "source_rows_missing",
    ]
    assert report["blockers"][0]["fail_closed"] is True


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    cache_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    source_path = tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    source_path.write_text(json.dumps(_source_quality()), encoding="utf-8")

    report = ledger.build_source_usefulness_ledger(repo_root=tmp_path)
    paths = ledger.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_source_usefulness_ledger/latest.json",
        "timestamped": "logs/qre_source_usefulness_ledger/ready.json",
        "history": "logs/qre_source_usefulness_ledger/history.jsonl",
        "operator_summary": "logs/qre_source_usefulness_ledger/operator_summary.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
    assert ledger.read_ledger_status(
        repo_root=tmp_path,
        output_dir=Path("logs/qre_source_usefulness_ledger"),
    ) == {
        "status": "ready",
        "research_ready": True,
        "path": "logs/qre_source_usefulness_ledger/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_safety_invariants_keep_ledger_read_only(tmp_path: Path) -> None:
    cache_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    source_path = tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(_cache_manifest()), encoding="utf-8")
    source_path.write_text(json.dumps(_source_quality()), encoding="utf-8")

    report = ledger.build_source_usefulness_ledger(repo_root=tmp_path)

    assert report["safety_invariants"] == {
        "read_only": True,
        "fetches_external_data": False,
        "mutates_cache": False,
        "mutates_research_outputs": False,
        "frozen_contracts_unchanged": True,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
        "source_usefulness_is_not_alpha": True,
        "source_usefulness_is_not_trading_authority": True,
    }
