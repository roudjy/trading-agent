from __future__ import annotations

import json
from pathlib import Path

from research.equity_factors import controlled_factor_evaluation_manifest as manifest


def test_controlled_factor_evaluation_manifest_writes_artifact(tmp_path: Path) -> None:
    paths = manifest.write_outputs(repo_root=tmp_path)
    assert (
        paths["latest"]
        == "artifacts/equity_factors/controlled_factor_evaluation_readiness_latest.v1.json"
    )
    payload = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    assert payload["report_kind"] == "controlled_factor_evaluation_readiness"


def test_controlled_factor_evaluation_manifest_refuses_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "bad.json"
    try:
        manifest._validate_write_target(bad)
    except ValueError as exc:
        assert "outside allowlist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
