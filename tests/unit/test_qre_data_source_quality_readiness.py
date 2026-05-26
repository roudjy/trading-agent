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
    assert report["rows"][0]["readiness_blockers"] == []
    assert report["summary"]["readiness_blocker_category_counts"] == {}
    assert report["summary"]["readiness_blocker_reason_counts"] == {}
    assert "high-confidence source identity" in report["summary"]["operator_summary"]
    assert report["reference_taxonomy"]["runtime_activation"] is False


def test_source_quality_blocks_unknown_identity_without_guessing() -> None:
    report = readiness.build_source_quality_report(
        _manifest(_manifest_row(source="unknown")),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["source_quality_ready"] is False
    assert report["summary"]["identity_confidence_counts"] == {"low": 1}
    assert report["summary"]["blocking_reason_counts"] == {"identity_not_high_confidence": 1}
    assert report["summary"]["readiness_blocker_category_counts"] == {"identity": 1}
    assert report["summary"]["readiness_blocker_reason_counts"] == {
        "identity_source_unknown": 1
    }
    assert report["rows"][0]["quality_status"] == "blocked"
    assert report["rows"][0]["blocking_reasons"] == ["identity_not_high_confidence"]
    assert report["rows"][0]["readiness_blockers"] == [
        {
            "category": "identity",
            "reason": "identity_source_unknown",
            "evidence_field": "source",
            "evidence_status": "missing_or_unknown",
            "fail_closed": True,
            "operator_explanation": (
                "Identity evidence field source is missing or unknown; "
                "source readiness fails closed until the manifest identifies it."
            ),
        }
    ]


def test_source_quality_blocks_missing_identity_evidence_by_field() -> None:
    report = readiness.build_source_quality_report(
        _manifest(
            _manifest_row(
                source=None,
                instrument="",
                timeframe="unknown",
                cache_kind=None,
            )
        ),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["identity_confidence_counts"] == {"unknown": 1}
    assert report["summary"]["readiness_blocker_category_counts"] == {"identity": 4}
    assert report["summary"]["readiness_blocker_reason_counts"] == {
        "identity_cache_kind_unknown": 1,
        "identity_instrument_unknown": 1,
        "identity_source_unknown": 1,
        "identity_timeframe_unknown": 1,
    }
    assert all(
        blocker["fail_closed"] is True
        for blocker in report["rows"][0]["readiness_blockers"]
    )


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
    assert report["summary"]["readiness_blocker_category_counts"] == {
        "data": 1,
        "source": 1,
    }
    assert report["summary"]["readiness_blocker_reason_counts"] == {
        "data_timestamp_range_missing": 1,
        "source_manifest_status_not_ready": 1,
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
    assert report["summary"]["report_readiness_blockers"] == [
        {
            "category": "source",
            "reason": "source_manifest_research_not_ready",
            "evidence_field": "summary.research_ready",
            "evidence_status": "false_or_missing",
            "fail_closed": True,
            "operator_explanation": (
                "The upstream cache manifest is not research-ready; source "
                "readiness fails closed."
            ),
        }
    ]


def test_source_quality_fails_closed_without_manifest_rows() -> None:
    report = readiness.build_source_quality_report(
        _manifest(ready=False),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["source_quality_ready"] is False
    assert report["summary"]["file_count"] == 0
    assert report["summary"]["operator_summary"] == (
        "No manifest file rows are available; data/source/identity readiness "
        "fails closed."
    )
    assert report["summary"]["report_readiness_blockers"] == [
        {
            "category": "data",
            "reason": "data_source_rows_missing",
            "evidence_field": "files",
            "evidence_status": "missing",
            "fail_closed": True,
            "operator_explanation": (
                "No manifest file rows are available, so data/source/identity "
                "readiness cannot be established."
            ),
        },
        {
            "category": "source",
            "reason": "source_manifest_research_not_ready",
            "evidence_field": "summary.research_ready",
            "evidence_status": "false_or_missing",
            "fail_closed": True,
            "operator_explanation": (
                "The upstream cache manifest is not research-ready; source "
                "readiness fails closed."
            ),
        },
    ]


def test_source_quality_blocks_missing_data_and_source_evidence() -> None:
    report = readiness.build_source_quality_report(
        _manifest(
            _manifest_row(
                row_count=None,
                min_timestamp_utc=None,
                max_timestamp_utc=None,
                content_hash=None,
            )
        ),
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["readiness_blocker_category_counts"] == {
        "data": 2,
        "source": 1,
    }
    assert report["summary"]["readiness_blocker_reason_counts"] == {
        "data_row_count_not_positive": 1,
        "data_timestamp_range_missing": 1,
        "source_content_hash_missing": 1,
    }
    assert "data/source/identity readiness blockers" in report["summary"][
        "operator_summary"
    ]


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
        "addendum3_reference_taxonomy_only": True,
        "activates_addendum3_runtime": False,
        "source_quality_as_alpha": False,
        "source_quality_as_promotion_authority": False,
    }
    assert set(readiness.READINESS_BLOCKER_CATEGORIES) == {
        "data",
        "source",
        "identity",
    }
