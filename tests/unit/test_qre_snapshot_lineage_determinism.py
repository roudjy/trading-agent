from __future__ import annotations

from pathlib import Path

from packages.qre_research.alpha_discovery import snapshot_lineage


def _truth_with_single_snapshot(root: Path, *, fingerprint: str = "fp-1", order: tuple[str, ...] = ("alpha",), mtime: str | None = None) -> dict[str, object]:
    physical_files = []
    for name in order:
        shard = root / "tmp" / f"{name}.parquet"
        physical_files.append(
            {
                "portable_relative_path": "",
                "physical_path": str(shard),
                "row_count": 120,
                "dataset_fingerprint": fingerprint,
                "effective_research_quality_status": "ready",
                "complete_bar_end": mtime,
            }
        )
    return {
        "census": {"physical_files": physical_files},
        "catalog": {"content_identity": "catalog-1"},
    }


def test_snapshot_lineage_identity_is_cross_root_deterministic(monkeypatch, tmp_path: Path) -> None:
    roots = [tmp_path / "root-a", tmp_path / "root-b"]
    payloads = []
    truths = {
        root: _truth_with_single_snapshot(root, mtime=None)
        for root in roots
    }

    monkeypatch.setattr(snapshot_lineage, "materialize_data_truth", lambda repo_root, force_refresh=False: truths[repo_root])

    for root in roots:
        payloads.append(snapshot_lineage.materialize_snapshot_lineage(root, write_outputs=False))

    assert payloads[0]["snapshot_lineage"]["content_identity"] == payloads[1]["snapshot_lineage"]["content_identity"]
    assert payloads[0]["snapshot_lineage"]["rows"] == payloads[1]["snapshot_lineage"]["rows"]


def test_snapshot_lineage_identity_is_order_and_mtime_independent(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    truths = [
        _truth_with_single_snapshot(repo_root, order=("b", "a"), mtime="2026-07-04T10:00:00Z"),
        _truth_with_single_snapshot(repo_root, order=("a", "b"), mtime="2026-07-05T11:11:11Z"),
    ]
    index = {"value": 0}

    def _fake_truth(repo_root: Path, force_refresh: bool = False) -> dict[str, object]:
        current = truths[index["value"]]
        index["value"] += 1
        return current

    monkeypatch.setattr(snapshot_lineage, "materialize_data_truth", _fake_truth)

    first = snapshot_lineage.materialize_snapshot_lineage(repo_root, write_outputs=False, force_refresh=True)
    second = snapshot_lineage.materialize_snapshot_lineage(repo_root, write_outputs=False, force_refresh=True)

    assert first["snapshot_lineage"]["content_identity"] == second["snapshot_lineage"]["content_identity"]


def test_snapshot_lineage_identity_changes_for_semantic_content_mutation(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    truths = [
        _truth_with_single_snapshot(repo_root, fingerprint="fp-a"),
        _truth_with_single_snapshot(repo_root, fingerprint="fp-b"),
    ]
    index = {"value": 0}

    def _fake_truth(repo_root: Path, force_refresh: bool = False) -> dict[str, object]:
        current = truths[index["value"]]
        index["value"] += 1
        return current

    monkeypatch.setattr(snapshot_lineage, "materialize_data_truth", _fake_truth)

    first = snapshot_lineage.materialize_snapshot_lineage(repo_root, write_outputs=False, force_refresh=True)
    second = snapshot_lineage.materialize_snapshot_lineage(repo_root, write_outputs=False, force_refresh=True)

    assert first["snapshot_lineage"]["content_identity"] != second["snapshot_lineage"]["content_identity"]


def test_snapshot_lineage_uses_logical_dataset_integrity_without_synthetic_coverage(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    truth = {
        "catalog": {
            "datasets": [
                {
                    "dataset_id": "certified_crypto_vendor|BTC-USD|1h",
                    "dataset_fingerprint": "sha256:logical",
                    "source_id": "certified_crypto_vendor",
                    "instrument_ids": ["BTC-USD"],
                    "timeframe": "1h",
                    "start": "2026-01-01T00:00:00Z",
                    "end": "2026-01-02T23:00:00Z",
                    "partition_refs": ["data/cache/market/certified_crypto_vendor__BTC-USD__1h__20260101__20260102__abcd.parquet"],
                    "integrity_summary": {
                        "raw_row_count": 48,
                        "unique_bar_count": 48,
                        "expected_bar_count": 48,
                        "coverage_ratio": 1.0,
                        "exact_duplicate_row_count": 0,
                        "overlapping_row_count": 0,
                        "conflicting_row_count": 0,
                        "invalid_row_count": 0,
                    },
                    "quality_summary": {
                        "row_integrity_status": "ready",
                        "effective_research_quality_status": "blocked",
                    },
                    "provenance": {"manifest_latest": "logs/qre_data_cache_manifest/latest.json"},
                }
            ],
            "content_identity": "catalog-identity",
        },
        "census": {
            "physical_files": [
                {
                    "portable_relative_path": "data/cache/market/certified_crypto_vendor__BTC-USD__1h__20260101__20260102__abcd.parquet",
                    "dataset_fingerprint": "sha256:physical",
                    "row_count": 5,
                    "effective_research_quality_status": "blocked",
                }
            ],
            "logical_datasets": [
                {
                    "dataset_id": "certified_crypto_vendor|BTC-USD|1h",
                    "dataset_fingerprint": "sha256:logical",
                    "source_id": "certified_crypto_vendor",
                    "instrument_ids": ["BTC-USD"],
                    "timeframe": "1h",
                    "start": "2026-01-01T00:00:00Z",
                    "end": "2026-01-02T23:00:00Z",
                    "partition_refs": ["data/cache/market/certified_crypto_vendor__BTC-USD__1h__20260101__20260102__abcd.parquet"],
                    "integrity_summary": {
                        "raw_row_count": 48,
                        "unique_bar_count": 48,
                        "expected_bar_count": 48,
                        "coverage_ratio": 1.0,
                        "exact_duplicate_row_count": 0,
                        "overlapping_row_count": 0,
                        "conflicting_row_count": 0,
                        "invalid_row_count": 0,
                    },
                    "quality_summary": {"row_integrity_status": "ready"},
                    "provenance": {"manifest_latest": "logs/qre_data_cache_manifest/latest.json"},
                }
            ],
        },
    }
    monkeypatch.setattr(snapshot_lineage, "materialize_data_truth", lambda repo_root, force_refresh=False: truth)

    payload = snapshot_lineage.materialize_snapshot_lineage(repo_root, write_outputs=False, force_refresh=True)
    rows = payload["snapshot_lineage"]["rows"]

    assert len(rows) == 1
    assert rows[0]["unique_bar_count"] == 48
    assert rows[0]["expected_bar_count"] == 48
    assert rows[0]["coverage_ratio"] == 1.0
    assert rows[0]["qualification_status"] == "COHERENT"
