from __future__ import annotations

import json
from pathlib import Path

from research.external_intelligence import source_manifest_registry as registry


def test_source_manifest_registry_is_deterministic_and_fail_closed() -> None:
    left = registry.build_source_manifest_registry()
    right = registry.build_source_manifest_registry()
    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    assert left["summary"]["quality_gated_eligible_providers"] == []
    assert left["summary"]["active_read_only_eligible_providers"] == []


def test_required_stub_manifests_exist_and_none_are_active_read_only() -> None:
    payload = registry.build_source_manifest_registry()
    source_ids = {row["source_id"] for row in payload["rows"]}
    assert "sec_companyfacts_manifest" in source_ids
    assert "openfigi_symbology_manifest" in source_ids
    assert "euronext_issuer_metadata_manifest" in source_ids
    assert "nasdaq_listings_metadata_manifest" in source_ids
    assert "nyse_listings_metadata_manifest" in source_ids
    assert all(row["source_status"] != "active_read_only" for row in payload["rows"])


def test_manifest_writer_creates_expected_sidecars(tmp_path: Path) -> None:
    paths = registry.write_outputs(repo_root=tmp_path)
    manifests = json.loads((tmp_path / paths["source_manifests"]).read_text(encoding="utf-8"))
    license_policy = json.loads((tmp_path / paths["source_license_policy"]).read_text(encoding="utf-8"))
    quality = json.loads((tmp_path / paths["source_manifest_quality"]).read_text(encoding="utf-8"))
    assert manifests["report_kind"] == "source_manifest_registry"
    assert license_policy["report_kind"] == "source_license_policy"
    assert quality["report_kind"] == "source_manifest_quality"
