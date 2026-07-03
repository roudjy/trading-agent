from __future__ import annotations

from pathlib import Path

import pandas as pd

from packages.qre_data.bar_integrity import build_unique_bar_integrity


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_overlapping_identical_shards_collapse_to_unique_bars(tmp_path: Path) -> None:
    repo_root = tmp_path
    path_a = repo_root / "data/cache/market/a.parquet"
    path_b = repo_root / "data/cache/market/b.parquet"
    rows = [
        {"timestamp_utc": "2026-01-01T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10},
        {"timestamp_utc": "2026-01-02T00:00:00Z", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 11},
    ]
    _write_parquet(path_a, rows)
    _write_parquet(path_b, rows)

    integrity = build_unique_bar_integrity(
        repo_root=repo_root,
        partitions=["data/cache/market/a.parquet", "data/cache/market/b.parquet"],
        instrument_id="AAPL",
        timeframe="1d",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
    )

    assert integrity.raw_row_count == 4
    assert integrity.unique_bar_count == 2
    assert integrity.exact_duplicate_row_count == 2
    assert integrity.conflicting_row_count == 0
    assert integrity.impossible_bar_density is False


def test_conflicting_same_timestamp_blocks_empirical_integrity(tmp_path: Path) -> None:
    repo_root = tmp_path
    path_a = repo_root / "data/cache/market/a.parquet"
    path_b = repo_root / "data/cache/market/b.parquet"
    _write_parquet(path_a, [{"timestamp_utc": "2026-01-01T00:00:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10}])
    _write_parquet(path_b, [{"timestamp_utc": "2026-01-01T00:00:00Z", "open": 9.0, "high": 9.5, "low": 8.5, "close": 9.1, "volume": 10}])

    integrity = build_unique_bar_integrity(
        repo_root=repo_root,
        partitions=["data/cache/market/a.parquet", "data/cache/market/b.parquet"],
        instrument_id="AAPL",
        timeframe="1d",
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T00:00:00Z",
    )

    assert integrity.conflicting_row_count == 1
    assert integrity.unique_bar_count == 0
    assert integrity.conflict_intervals == ("2026-01-01T00:00:00Z",)


def test_impossible_24_7_density_is_detected(tmp_path: Path) -> None:
    repo_root = tmp_path
    path_a = repo_root / "data/cache/market/impossible.parquet"
    rows = [
        {"timestamp_utc": f"2026-01-01T00:{minute:02d}:00Z", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10}
        for minute in range(5)
    ]
    _write_parquet(path_a, rows)
    integrity = build_unique_bar_integrity(
        repo_root=repo_root,
        partitions=["data/cache/market/impossible.parquet"],
        instrument_id="BTC-USD",
        timeframe="1h",
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T00:00:00Z",
    )
    assert integrity.expected_bar_count == 1
    assert integrity.unique_bar_count == 5
    assert integrity.impossible_bar_density is True
