from __future__ import annotations

from pathlib import Path

from packages.qre_data import source_quality_readiness
from research import qre_source_lifecycle_quality_gate as report


def _manifest_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "summary": {"research_ready": True},
        "files": [
            {
                "path": "data/cache/market/yfinance__AAPL__1d__20260401__20260402__abc123.parquet",
                "cache_kind": "market",
                "source": "yfinance",
                "instrument": "AAPL",
                "timeframe": "1d",
                "status": "ready",
                "row_count": 1,
                "min_timestamp_utc": "2026-04-01T00:00:00Z",
                "max_timestamp_utc": "2026-04-01T00:00:00Z",
                "content_hash": "sha256:abc123",
            }
        ],
    }


def _seed_source_quality(tmp_path: Path) -> None:
    manifest_payload = _manifest_payload()
    source_payload = source_quality_readiness.build_source_quality_report(
        manifest_payload,
        generated_at_utc="2026-06-15T00:00:00Z",
    )
    source_quality_readiness.write_source_quality_outputs(
        source_payload,
        output_dir=Path("logs/qre_data_source_quality_readiness"),
        repo_root=tmp_path,
    )


def test_report_fails_closed_without_source_quality_status(tmp_path: Path) -> None:
    payload = report.build_source_lifecycle_quality_gate(repo_root=tmp_path)

    assert payload["summary"]["source_quality_report_ready"] is False
    assert payload["summary"]["active_read_only_ready_count"] == 0
    assert payload["summary"]["quality_gated_ready_count"] == 0
    assert payload["summary"]["active_read_only_blocking_reason_counts"][
        "quality_gates_passed"
    ] > 0
    assert "transition_requires_quality_gated_state" in payload["summary"][
        "active_read_only_blocking_reason_counts"
    ]


def test_report_keeps_current_manifests_fail_closed_even_with_ready_source_quality(
    tmp_path: Path,
) -> None:
    _seed_source_quality(tmp_path)

    payload = report.build_source_lifecycle_quality_gate(repo_root=tmp_path)
    paths = report.write_outputs(payload, repo_root=tmp_path)

    assert payload["summary"]["source_quality_report_ready"] is True
    assert payload["summary"]["active_read_only_ready_count"] == 0
    assert payload["summary"]["quality_gated_ready_count"] == 0
    assert payload["summary"]["lifecycle_status_counts"]["blocked"] == payload["summary"][
        "source_count"
    ]
    assert payload["supporting_reports"]["source_manifest_registry"][
        "active_read_only_eligible_providers"
    ] == []
    assert paths["latest"] == "logs/qre_source_lifecycle_quality_gate/latest.json"
    assert paths["operator_summary"] == "logs/qre_source_lifecycle_quality_gate/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(report.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token
