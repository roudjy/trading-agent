from __future__ import annotations

import json
from pathlib import Path

from research.data_readiness import fundamental_readiness_manifest as manifest


def test_fundamental_readiness_manifest_writes_expected_sidecars(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    readiness = json.loads((tmp_path / paths["fundamental_readiness"]).read_text(encoding="utf-8"))
    coverage = json.loads((tmp_path / paths["factor_field_coverage"]).read_text(encoding="utf-8"))
    assert readiness["report_kind"] == "fundamental_readiness"
    assert coverage["report_kind"] == "factor_field_coverage"


def test_fundamental_readiness_manifest_is_research_only() -> None:
    payload = manifest.build_fundamental_readiness()
    assert payload["safety_invariants"]["research_only"] is True
    assert payload["safety_invariants"]["paper_shadow_live_forbidden"] is True
