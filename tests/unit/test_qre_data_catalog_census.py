from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from packages.qre_data.dataset_catalog import build_data_census, materialize_data_truth


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prepare_repo(repo_root: Path, *, path_value: str | None = None) -> None:
    cache_dir = repo_root / "data/cache/market"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "yfinance__AAPL__1d__20260408__20260415__fixture.parquet"
    pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2026-04-08", periods=5, freq="D", tz="UTC"),
            "open": [1.0, 2.0, 3.0, 4.0, 5.0],
            "high": [2.0, 3.0, 4.0, 5.0, 6.0],
            "low": [0.0, 1.0, 2.0, 3.0, 4.0],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5],
            "volume": [10, 11, 12, 13, 14],
        }
    ).to_parquet(path, index=False)
    manifest_path = path_value or path.relative_to(repo_root).as_posix()
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_data_cache_manifest",
            "summary": {"research_ready": True},
            "files": [
                {
                    "path": manifest_path,
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
                    "file_count": 1,
                    "row_count": 5,
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "max_timestamp_utc": "2026-04-12T00:00:00Z",
                    "content_hash": "sha256:testcov",
                    "status_counts": {"ready": 1},
                    "ready": True,
                }
            ],
        },
    )


def test_census_marks_machine_specific_paths_as_non_portable(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    absolute_like = "C:/Users/example/trading-agent/data/cache/market/yfinance__AAPL__1d__20260408__20260415__fixture.parquet"
    _prepare_repo(repo_root, path_value=absolute_like)

    census = build_data_census(repo_root)

    assert census["physical_files"][0]["machine_specific_path"] is True


def test_materialize_data_truth_writes_catalog_and_reconciliation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_repo(repo_root)

    truth = materialize_data_truth(repo_root)

    assert truth["catalog"]["datasets"]
    assert truth["reconciliation"]["root_cause"]["causes"]
    assert (repo_root / "generated_research/data_catalog/census/latest.json").is_file()
    assert (repo_root / "generated_research/data_catalog/catalog/latest.json").is_file()
