from __future__ import annotations

import json
from pathlib import Path

from research.data_readiness import factor_field_coverage_manifest as manifest


def test_factor_field_coverage_manifest_writes_expected_sidecar(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    payload = json.loads((tmp_path / paths["factor_field_coverage"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "factor_field_coverage"
    assert payload["summary"]["covered_count"] == 0


def test_factor_field_coverage_manifest_is_deterministic() -> None:
    first = manifest.build_factor_field_coverage()
    second = manifest.build_factor_field_coverage()
    assert first == second
