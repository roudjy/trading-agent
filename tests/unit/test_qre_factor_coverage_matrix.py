from __future__ import annotations

import json
from pathlib import Path

from research import qre_factor_coverage_matrix as report_module


def test_qre_factor_coverage_matrix_is_deterministic() -> None:
    left = report_module.build_qre_factor_coverage_matrix()
    right = report_module.build_qre_factor_coverage_matrix()
    assert left == right
    assert left["summary"]["approved_provider_count"] == 0
    assert left["safety_invariants"]["provider_is_not_alpha_authority"] is True


def test_qre_factor_coverage_matrix_preserves_report_only_provider_scope() -> None:
    report = report_module.build_qre_factor_coverage_matrix()
    provider_rows = {row["provider_id"]: row for row in report["provider_rows"]}

    assert provider_rows["sec_companyfacts"]["approval_status"] == "CANDIDATE_ONLY"
    assert provider_rows["sec_companyfacts"]["provider_alpha_authority"] is False
    assert provider_rows["sec_companyfacts"]["freshness_status"] == "UNKNOWN"


def test_qre_factor_coverage_matrix_write_outputs(tmp_path: Path) -> None:
    report = report_module.build_qre_factor_coverage_matrix()
    paths = report_module.write_outputs(report, repo_root=tmp_path)
    payload = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "qre_factor_coverage_matrix"
    operator_summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert "# QRE Factor Coverage Matrix" in operator_summary
    assert "provider_count" in operator_summary
