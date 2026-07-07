from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from packages.qre_research.alpha_discovery.source_qualification import (
    SOURCE_BLOCKED,
    SOURCE_SCREENING_ELIGIBLE,
)
from research.qre_source_onboarding import (
    import_local_source,
    qualify_onboarded_source,
    summarize_onboarding,
    validate_manifest_file,
)

FIXTURES = Path("tests/fixtures/source_onboarding")


def _write_crypto_bars(path: Path, *, count: int = 48, reverse: bool = False, conflict: bool = False) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for idx in range(count):
        ts = start + timedelta(hours=idx)
        rows.append(
            {
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "symbol": "BTC-USD",
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 10 + idx,
            }
        )
    if conflict:
        rows.append({**rows[0], "close": 100.75})
    if reverse:
        rows = list(reversed(rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "symbol", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def _write_weekday_bars(path: Path, *, count: int = 48) -> None:
    current = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    while len(rows) < count:
        if current.weekday() < 5:
            idx = len(rows)
            rows.append(
                {
                    "timestamp": current.isoformat().replace("+00:00", "Z"),
                    "symbol": "TEST",
                    "open": 50 + idx,
                    "high": 51 + idx,
                    "low": 49 + idx,
                    "close": 50.5 + idx,
                    "volume": 100 + idx,
                }
            )
        current += timedelta(days=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "symbol", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def test_manual_only_manifest_validation_does_not_request_screening_attestation() -> None:
    result = validate_manifest_file(FIXTURES / "crypto_24_7_missing_license" / "manifest.yaml")

    assert result["valid"] is True
    assert "missing_license_attestation" not in result["operator_actions"]
    assert "provide_screening_license_attestation" not in result["operator_actions"]


def test_screening_manifest_validation_requires_explicit_source_status(tmp_path: Path) -> None:
    manifest = yaml.safe_load((FIXTURES / "crypto_24_7_good" / "manifest.yaml").read_text(encoding="utf-8"))
    manifest.pop("source_status")
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")

    result = validate_manifest_file(path)

    assert result["valid"] is False
    assert "missing_source_status" in result["operator_actions"]
    assert "set_screening_source_status" in result["operator_actions"]
    assert "provide_screening_license_attestation" not in result["operator_actions"]


def test_screening_manifest_validation_rejects_manual_only_source_status(tmp_path: Path) -> None:
    manifest = yaml.safe_load((FIXTURES / "crypto_24_7_good" / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["source_status"] = "manual_research_only"
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")

    result = validate_manifest_file(path)

    assert result["valid"] is False
    assert "invalid_screening_source_status" in result["operator_actions"]
    assert "set_screening_source_status" in result["operator_actions"]


def test_cli_module_entrypoint_emits_json() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "research.qre_source_onboarding",
            "validate-manifest",
            "--manifest",
            str(FIXTURES / "crypto_24_7_good" / "manifest.yaml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["valid"] is True
    assert payload["source_id"] == "local_crypto_screening_fixture"


def test_local_import_and_qualification_promotes_good_crypto_fixture(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    _write_crypto_bars(bars)

    imported = import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "crypto_24_7_good" / "manifest.yaml",
        bars_path=bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_screening_fixture/snap-good",
        snapshot_id="snap-good",
    )
    qualified = qualify_onboarded_source(repo_root=tmp_path, source_id="local_crypto_screening_fixture", snapshot_id="snap-good")
    row = qualified["source_qualification"]["rows"][0]
    resolution_row = qualified["source_resolution"]["rows"][0]

    assert imported["import_audit"]["unique_bar_count"] == 48
    assert imported["import_audit"]["expected_bar_count"] == 48
    assert imported["import_audit"]["coverage_ratio"] == 1.0
    assert row["allowed_evidence_tier"] == SOURCE_SCREENING_ELIGIBLE
    assert row["reason_codes"] == []
    assert resolution_row["trading_authority"] is False
    assert resolution_row["operator_action_required"] is False


def test_missing_license_fixture_stays_blocked_without_false_promotion(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    _write_crypto_bars(bars)

    import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "crypto_24_7_missing_license" / "manifest.yaml",
        bars_path=bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_missing_license_fixture/snap-missing-license",
        snapshot_id="snap-missing-license",
    )
    qualified = qualify_onboarded_source(repo_root=tmp_path, source_id="local_crypto_missing_license_fixture", snapshot_id="snap-missing-license")
    row = qualified["source_qualification"]["rows"][0]

    assert row["allowed_evidence_tier"] == SOURCE_BLOCKED
    assert "source_license_not_screening_eligible" in row["reason_codes"]
    assert qualified["onboarding"]["operator_actions"] == ["provide_screening_license_attestation"]


def test_manual_research_only_source_with_pass_license_is_not_screening_promoted(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    _write_crypto_bars(bars)
    manifest = yaml.safe_load((FIXTURES / "crypto_24_7_good" / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["source_id"] = "local_crypto_manual_only_fixture"
    manifest["source_status"] = "manual_research_only"
    manifest["allowed_use"] = ["manual_research"]
    manifest_path = tmp_path / "manual_only_manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")

    validation = validate_manifest_file(manifest_path)
    import_local_source(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        bars_path=bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_manual_only_fixture/snap-manual",
        snapshot_id="snap-manual",
    )
    qualified = qualify_onboarded_source(repo_root=tmp_path, source_id="local_crypto_manual_only_fixture", snapshot_id="snap-manual")
    row = qualified["source_qualification"]["rows"][0]
    resolution_row = qualified["source_resolution"]["rows"][0]

    assert validation["valid"] is True
    assert row["allowed_evidence_tier"] == SOURCE_BLOCKED
    assert "source_license_not_screening_eligible" in row["reason_codes"]
    assert resolution_row["trading_authority"] is False


def test_bad_coverage_and_conflicting_duplicates_block(tmp_path: Path) -> None:
    low_bars = tmp_path / "low.csv"
    conflict_bars = tmp_path / "conflict.csv"
    _write_crypto_bars(low_bars, count=40)
    _write_crypto_bars(conflict_bars, conflict=True)

    import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "crypto_24_7_insufficient_coverage" / "manifest.yaml",
        bars_path=low_bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_low_coverage_fixture/snap-low",
        snapshot_id="snap-low",
        requested_end="2026-01-02T23:00:00Z",
    )
    low = qualify_onboarded_source(repo_root=tmp_path, source_id="local_crypto_low_coverage_fixture", snapshot_id="snap-low")

    import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "crypto_24_7_conflicts" / "manifest.yaml",
        bars_path=conflict_bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_conflict_fixture/snap-conflict",
        snapshot_id="snap-conflict",
    )
    conflict = qualify_onboarded_source(repo_root=tmp_path, source_id="local_crypto_conflict_fixture", snapshot_id="snap-conflict")

    assert "insufficient_coverage" in low["source_qualification"]["rows"][0]["reason_codes"]
    assert "conflicting_rows_present" in conflict["source_qualification"]["rows"][0]["reason_codes"]


def test_weekday_daily_fixture_is_supported(tmp_path: Path) -> None:
    bars = tmp_path / "weekday.csv"
    _write_weekday_bars(bars)

    imported = import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "weekday_daily_good" / "manifest.yaml",
        bars_path=bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_weekday_screening_fixture/snap-weekday",
        snapshot_id="snap-weekday",
    )
    qualified = qualify_onboarded_source(repo_root=tmp_path, source_id="local_weekday_screening_fixture", snapshot_id="snap-weekday")

    assert imported["import_audit"]["expected_bar_count"] == 48
    assert qualified["source_qualification"]["rows"][0]["allowed_evidence_tier"] == SOURCE_SCREENING_ELIGIBLE


def test_onboarding_identity_is_order_root_mtime_and_manifest_order_deterministic(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    bars_a = root_a / "bars.csv"
    bars_b = root_b / "bars.csv"
    _write_crypto_bars(bars_a)
    _write_crypto_bars(bars_b, reverse=True)
    os.utime(bars_b, (1_800_000_000, 1_800_000_000))

    first = import_local_source(
        repo_root=root_a,
        manifest_path=FIXTURES / "crypto_24_7_good" / "manifest.yaml",
        bars_path=bars_a,
        out_dir=root_a / "generated_research/data_catalog/imports/local_crypto_screening_fixture/snap-deterministic",
        snapshot_id="snap-deterministic",
    )
    original_manifest = yaml.safe_load((FIXTURES / "crypto_24_7_good" / "manifest.yaml").read_text(encoding="utf-8"))
    reordered_manifest = root_b / "manifest.yaml"
    reordered_manifest.parent.mkdir(parents=True, exist_ok=True)
    reordered_manifest.write_text(yaml.safe_dump(dict(reversed(list(original_manifest.items()))), sort_keys=False), encoding="utf-8")
    second = import_local_source(
        repo_root=root_b,
        manifest_path=reordered_manifest,
        bars_path=bars_b,
        out_dir=root_b / "generated_research/data_catalog/imports/local_crypto_screening_fixture/snap-deterministic",
        snapshot_id="snap-deterministic",
    )

    assert first["source_manifest"]["manifest_hash"] == second["source_manifest"]["manifest_hash"]
    assert first["import_audit"]["data_fingerprint"] == second["import_audit"]["data_fingerprint"]
    assert first["snapshot"]["content_identity"] == second["snapshot"]["content_identity"]


def test_fake_secret_is_not_written_to_outputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QRE_DATABENTO_API_KEY", "fake-secret-value")
    bars = tmp_path / "bars.csv"
    _write_crypto_bars(bars)

    payload = import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "crypto_24_7_good" / "manifest.yaml",
        bars_path=bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_screening_fixture/snap-secret",
        snapshot_id="snap-secret",
    )

    serialized = json.dumps(payload, sort_keys=True)
    assert "fake-secret-value" not in serialized


def test_summarize_reports_current_onboarding_state(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    _write_crypto_bars(bars)
    import_local_source(
        repo_root=tmp_path,
        manifest_path=FIXTURES / "crypto_24_7_good" / "manifest.yaml",
        bars_path=bars,
        out_dir=tmp_path / "generated_research/data_catalog/imports/local_crypto_screening_fixture/snap-summary",
        snapshot_id="snap-summary",
    )
    qualify_onboarded_source(repo_root=tmp_path, source_id="local_crypto_screening_fixture", snapshot_id="snap-summary")

    summary = summarize_onboarding(repo_root=tmp_path)

    assert summary["summary"]["source_count"] == 1
    assert summary["summary"]["screening_eligible_count"] == 1
