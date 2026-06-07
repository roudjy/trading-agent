from __future__ import annotations

import json
from pathlib import Path

from research.external_intelligence import fundamental_provider_manifest as manifest


def test_manifest_writes_expected_sidecars(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    candidates = json.loads((tmp_path / paths["candidates"]).read_text(encoding="utf-8"))
    summary = json.loads((tmp_path / paths["summary"]).read_text(encoding="utf-8"))
    assert candidates["report_kind"] == "fundamental_provider_candidates"
    assert summary["report_kind"] == "fundamental_provider_summary"


def test_manifest_summary_matches_registry_counts() -> None:
    payload = manifest.build_fundamental_provider_summary(
        manifest.build_fundamental_provider_registry()
    )
    assert payload["summary"]["total_providers"] >= 10
    assert payload["summary"]["active_read_only"] == 0
