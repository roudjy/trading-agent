from __future__ import annotations

import json
from pathlib import Path

from research import qre_bounded_generation_artifact_acceptance_verifier as verifier


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_verifier_rejects_context_only_and_stdout_only_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "legacy_context.json",
        {"preset_id": "trend_pullback_v1", "timeframe": "4h", "stdout_tail": "legacy"},
    )
    _write_json(
        tmp_path / "logs" / "current_candidate.json",
        {"symbol": "AAPL", "preset_id": "trend_pullback_continuation_daily_v1", "timeframe": "daily_v1"},
    )

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    rows = {row["relative_path"]: row for row in report["rows"]}

    assert rows["logs/legacy_context.json"]["classification"] == "rejected_stdout_only"
    assert rows["logs/current_candidate.json"]["classification"] == "rejected_missing_identity"
