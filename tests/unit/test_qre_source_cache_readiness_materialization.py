from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from packages.qre_data import cache_manifest
from packages.qre_data import source_quality_readiness
from research import qre_pre_shadow_paper_research_readiness as pre_shadow_readiness
from research import qre_source_cache_readiness_materialization as materialization


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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_cache_and_source_sidecars(tmp_path: Path) -> None:
    cache = tmp_path / "data" / "cache" / "market"
    _write_parquet(
        cache / "yfinance__AAPL__1d__20260401__20260402__abc123.parquet",
        [datetime(2026, 4, 1, 0, 0, tzinfo=UTC)],
    )
    manifest_payload = cache_manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-06-07T00:00:00Z",
    )
    cache_manifest.write_manifest_outputs(
        manifest_payload,
        output_dir=Path("logs/qre_data_cache_manifest"),
        repo_root=tmp_path,
    )
    source_payload = source_quality_readiness.build_source_quality_report(
        manifest_payload,
        generated_at_utc="2026-06-07T00:00:00Z",
    )
    source_quality_readiness.write_source_quality_outputs(
        source_payload,
        output_dir=Path("logs/qre_data_source_quality_readiness"),
        repo_root=tmp_path,
    )


def _seed_pre_shadow_supporting_files(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {"candidates": []},
    )
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})


def test_materialization_fails_closed_when_sidecars_are_missing(tmp_path: Path) -> None:
    report = materialization.build_source_cache_readiness_materialization(repo_root=tmp_path)

    assert report["summary"]["cache_manifest_sidecar_status"] == "missing"
    assert report["summary"]["source_quality_sidecar_status"] == "missing"
    assert report["summary"]["source_cache_readiness_linked"] is False
    assert report["summary"]["missing_sidecars"] == ["cache_manifest", "source_quality"]
    assert report["summary"]["blocking_reason_counts"] == {
        "cache_manifest_missing": 1,
        "source_quality_sidecar_missing": 1,
    }


def test_materialization_surfaces_present_ready_sidecars_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    _seed_cache_and_source_sidecars(tmp_path)

    report = materialization.build_source_cache_readiness_materialization(repo_root=tmp_path)
    paths = materialization.write_outputs(report, repo_root=tmp_path)

    assert report["summary"]["cache_manifest_sidecar_status"] == "present_ready"
    assert report["summary"]["source_quality_sidecar_status"] == "present_ready"
    assert report["summary"]["source_cache_readiness_linked"] is True
    assert report["summary"]["cache_coverage_row_count"] == 1
    assert report["summary"]["source_quality_row_count"] == 1
    assert "files" not in report["materialized_cache_manifest"]
    assert paths["latest"] == "logs/qre_source_cache_readiness_materialization/latest.json"
    assert paths["cache_manifest_artifact"] == "artifacts/cache/cache_manifest_latest.v1.json"
    assert paths["cache_coverage_artifact"] == "artifacts/cache/cache_coverage_latest.v1.json"
    assert (tmp_path / paths["cache_manifest_artifact"]).is_file()
    assert (tmp_path / paths["cache_coverage_artifact"]).is_file()


def test_pre_shadow_readiness_uses_explicit_materialized_source_cache_status(
    tmp_path: Path,
) -> None:
    _seed_pre_shadow_supporting_files(tmp_path)

    report = pre_shadow_readiness.build_pre_shadow_paper_research_readiness(
        repo_root=tmp_path,
        max_candidates=1,
    )

    assert report["summary"]["source_readiness_linked"] is False
    assert "cache_manifest" in str(report["summary"]["source_readiness_note"])
    assert "source_quality" in str(report["summary"]["source_readiness_note"])
    assert (
        report["supporting_reports"]["source_cache_materialization"]["cache_manifest_sidecar_status"]
        == "missing"
    )
