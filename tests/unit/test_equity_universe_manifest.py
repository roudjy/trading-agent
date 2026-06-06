from __future__ import annotations

import json
from pathlib import Path

from research import equity_universe_manifest as manifest


def test_manifest_write_outputs(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    assert paths["catalog"] == "artifacts/universe/equity_universe_catalog_latest.v1.json"
    assert paths["summary"] == "artifacts/universe/equity_universe_summary_latest.v1.json"
    assert paths["quality"] == "artifacts/universe/equity_universe_quality_latest.v1.json"
    assert paths["identity"] == "artifacts/identity/instrument_identity_latest.v1.json"
    payload = json.loads((tmp_path / paths["catalog"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "equity_universe_catalog"
    summary = json.loads((tmp_path / paths["summary"]).read_text(encoding="utf-8"))
    assert summary["report_kind"] == "equity_universe_summary"
    identity = json.loads((tmp_path / paths["identity"]).read_text(encoding="utf-8"))
    assert identity["report_kind"] == "instrument_identity"


def test_manifest_main_payload_shape() -> None:
    payload = {
        "catalog": manifest.build_equity_universe_catalog(),
        "summary": manifest.build_equity_universe_summary(),
        "quality": manifest.build_equity_universe_quality(),
        "identity": manifest.build_instrument_identity_report(),
    }
    assert payload["catalog"]["summary"]["instrument_count"] >= 100
    assert payload["quality"]["summary"]["ambiguous_mappings"] >= 1
