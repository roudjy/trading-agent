from __future__ import annotations

import json
from pathlib import Path

from research import equity_factor_manifest as manifest


def test_factor_manifest_writes_catalog_and_contracts(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    assert paths["catalog"] == "artifacts/equity_factors/equity_factor_catalog_latest.v1.json"
    assert (
        paths["contracts"]
        == "artifacts/equity_factors/equity_factor_calculation_contracts_latest.v1.json"
    )
    catalog = json.loads((tmp_path / paths["catalog"]).read_text(encoding="utf-8"))
    contracts = json.loads((tmp_path / paths["contracts"]).read_text(encoding="utf-8"))
    assert catalog["report_kind"] == "equity_factor_catalog"
    assert contracts["report_kind"] == "equity_factor_calculation_contracts"


def test_factor_manifest_payload_is_research_only() -> None:
    payload = {
        "catalog": manifest.build_equity_factor_catalog(),
        "contracts": manifest.build_equity_factor_calculation_contracts(),
    }
    assert payload["catalog"]["safety_invariants"]["research_only"] is True
    assert payload["contracts"]["safety_invariants"]["paper_shadow_live_forbidden"] is True
