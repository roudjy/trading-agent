from __future__ import annotations

import json
from pathlib import Path

from research import qre_sec_openfigi_manifest_hardening as report_module


def test_sec_openfigi_manifest_hardening_is_deterministic_and_fail_closed() -> None:
    left = report_module.build_sec_openfigi_manifest_hardening()
    right = report_module.build_sec_openfigi_manifest_hardening()
    assert left == right
    assert left["summary"]["quality_gated_unlock_allowed_count"] == 0
    assert left["summary"]["active_read_only_unlock_allowed_count"] == 0


def test_sec_openfigi_manifest_hardening_keeps_both_sources_as_readiness_inputs_only() -> None:
    report = report_module.build_sec_openfigi_manifest_hardening()
    rows = {row["source_id"]: row for row in report["rows"]}

    sec = rows["sec_companyfacts_manifest"]
    assert "fundamental_field_candidate" in sec["allowed_use"]
    assert "trade_signal" in sec["forbidden_use"]
    assert sec["quality_gated_readiness_input"] is True
    assert sec["alpha_authority"] is False
    assert sec["quality_gated_unlock_allowed"] is False

    openfigi = rows["openfigi_symbology_manifest"]
    assert "identity_mapping" in openfigi["allowed_use"]
    assert "fundamental_field_readiness" in openfigi["forbidden_use"]
    assert openfigi["readiness_input_kind"] == "identity_manifest_input_only"
    assert openfigi["alpha_authority"] is False
    assert openfigi["active_read_only_unlock_allowed"] is False


def test_sec_openfigi_manifest_hardening_writes_outputs(tmp_path: Path) -> None:
    report = report_module.build_sec_openfigi_manifest_hardening()
    paths = report_module.write_outputs(report, repo_root=tmp_path)
    payload = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "qre_sec_openfigi_manifest_hardening"
    summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert "# QRE SEC and OpenFIGI Manifest Hardening" in summary
