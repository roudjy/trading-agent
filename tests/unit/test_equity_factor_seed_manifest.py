from __future__ import annotations

import json
from pathlib import Path

from research.hypothesis_discovery import equity_factor_seed_manifest as manifest


def test_write_outputs_materializes_hypothesis_seed_artifact(tmp_path: Path) -> None:
    report = {
        "schema_version": "1.0",
        "report_kind": "equity_factor_hypothesis_seeds",
        "rows": [],
    }

    paths = manifest.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "artifacts/hypothesis_discovery/equity_factor_hypothesis_seeds_latest.v1.json"
    payload = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "equity_factor_hypothesis_seeds"


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "bad.json"
    try:
        manifest._validate_write_target(bad)
    except ValueError as exc:
        assert "outside allowlist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
