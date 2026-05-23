from __future__ import annotations

from pathlib import Path

from packages.qre_data import source_quality_readiness as readiness


def _manifest_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "path": "data/cache/market/yfinance__BTC-USD__1h__20260401__20260403__abc123.parquet",
        "cache_kind": "market",
        "source": "yfinance",
        "instrument": "BTC-USD",
        "timeframe": "1h",
        "status": "ready",
        "row_count": 3,
        "min_timestamp_utc": "2026-04-01T00:00:00Z",
        "max_timestamp_utc": "2026-04-01T02:00:00Z",
        "content_hash": "sha256:abc123",
    }
    row.update(overrides)
    return row


def _manifest(*rows: dict[str, object], ready: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "summary": {"research_ready": ready},
        "files": list(rows),
    }


def test_source_quality_report_marks_high_confidence_manifest_rows_ready() -> None:
    report = readiness.build_source_quality_report(
        _manifest(_manifest_row()),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_data_source_quality_readiness"
    assert report["summary"]["research_ready"] is True
    assert report["summary"]["source_quality_ready"] is True
    assert report["summary"]["identity_confidence_counts"] == {"high": 1}
    assert report["summary"]["quality_status_counts"] == {"ready": 1}
    assert report["rows"][0]["identity_confidence"] == "high"
    assert report["rows"][0]["quality_status"] == "ready"
    assert report["rows"][0]["blocking_reasons"] == []
    assert "high-confidence source identity" in report["summary"]["operator_summary"]


def test_source_quality_blocks_unknown_identity_without_guessing() -> None:
    report = readiness.build_source_quality_report(
        _manifest(_manifest_row(source="unknown")),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["source_quality_ready"] is False
    assert report["summary"]["identity_confidence_counts"] == {"low": 1}
    assert report["summary"]["blocking_reason_counts"] == {"identity_not_high_confidence": 1}
    assert report["rows"][0]["quality_status"] == "blocked"
    assert report["rows"][0]["blocking_reasons"] == ["identity_not_high_confidence"]


def test_source_quality_blocks_manifest_quality_failures() -> None:
    report = readiness.build_source_quality_report(
        _manifest(
            _manifest_row(
                status="missing_timestamp",
                row_count=4,
                min_timestamp_utc=None,
                max_timestamp_utc=None,
            )
        ),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["quality_status_counts"] == {"blocked": 1}
    assert report["summary"]["blocking_reason_counts"] == {
        "manifest_status_missing_timestamp": 1,
        "timestamp_range_missing": 1,
    }
    assert report["rows"][0]["operator_explanation"].startswith(
        "yfinance/BTC-USD/1h is not research-ready"
    )


def test_source_quality_fails_closed_when_manifest_is_not_ready() -> None:
    report = readiness.build_source_quality_report(
        _manifest(_manifest_row(), ready=False),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["source_quality_ready"] is True
    assert report["summary"]["manifest_research_ready"] is False
    assert report["summary"]["fail_closed"] is True


def test_source_quality_fails_closed_without_manifest_rows() -> None:
    report = readiness.build_source_quality_report(
        _manifest(ready=False),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["source_quality_ready"] is False
    assert report["summary"]["file_count"] == 0
    assert report["summary"]["operator_summary"] == (
        "No manifest file rows are available; source quality fails closed."
    )


def test_read_source_quality_status_fails_closed_until_report_exists(tmp_path: Path) -> None:
    missing = readiness.read_source_quality_status(
        output_dir=Path("logs/qre_data_source_quality_readiness"),
        repo_root=tmp_path,
    )

    assert missing == {
        "status": "missing_source_quality_report",
        "research_ready": False,
        "path": "logs/qre_data_source_quality_readiness/latest.json",
        "fails_closed": True,
    }

    report = readiness.build_source_quality_report(
        _manifest(_manifest_row()),
        generated_at_utc="2026-05-23T00:00:00Z",
    )
    readiness.write_source_quality_outputs(
        report,
        output_dir=Path("logs/qre_data_source_quality_readiness"),
        repo_root=tmp_path,
    )
    present = readiness.read_source_quality_status(
        output_dir=Path("logs/qre_data_source_quality_readiness"),
        repo_root=tmp_path,
    )

    assert present == {
        "status": "ready",
        "research_ready": True,
        "path": "logs/qre_data_source_quality_readiness/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_safety_invariants_keep_source_quality_read_only() -> None:
    report = readiness.build_source_quality_report(_manifest(_manifest_row()))

    assert report["safe_to_execute"] is False
    assert report["safety_invariants"] == {
        "read_only": True,
        "fetches_external_data": False,
        "activates_vendor_sources": False,
        "mutates_cache": False,
        "mutates_research_outputs": False,
        "frozen_contracts_unchanged": True,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
    }
