from __future__ import annotations

import json
from pathlib import Path

from research.data_readiness import fundamental_readiness_manifest as manifest


def test_fundamental_readiness_manifest_writes_expected_sidecars(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    readiness = json.loads((tmp_path / paths["fundamental_readiness"]).read_text(encoding="utf-8"))
    coverage = json.loads((tmp_path / paths["factor_field_coverage"]).read_text(encoding="utf-8"))
    point_in_time = json.loads((tmp_path / paths["point_in_time_policy"]).read_text(encoding="utf-8"))
    report_lag = json.loads((tmp_path / paths["report_lag_policy"]).read_text(encoding="utf-8"))
    restatement = json.loads((tmp_path / paths["restatement_policy"]).read_text(encoding="utf-8"))
    assert readiness["report_kind"] == "fundamental_readiness"
    assert coverage["report_kind"] == "factor_field_coverage"
    assert point_in_time["report_kind"] == "point_in_time_policy"
    assert report_lag["report_kind"] == "report_lag_policy"
    assert restatement["report_kind"] == "restatement_policy"


def test_fundamental_readiness_manifest_is_research_only() -> None:
    payload = manifest.build_fundamental_readiness()
    assert payload["safety_invariants"]["research_only"] is True
    assert payload["safety_invariants"]["paper_shadow_live_forbidden"] is True
