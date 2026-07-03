from __future__ import annotations

from pathlib import Path

from packages.qre_research.alpha_discovery.runner import _historical_reassessments


def test_historical_reassessments_preserve_mvp_provenance_but_remove_empirical_authority(tmp_path: Path) -> None:
    payload = _historical_reassessments(tmp_path)
    rows = {str(row.get("artifact_id") or ""): row for row in payload["rows"]}

    assert rows["qcam_4c691604bc936a8e"]["corrected_evidence_tier"] == "EXECUTOR_SMOKE"
    assert rows["qcam_4c691604bc936a8e"]["mechanism_prior_authority"] == "none"
    assert rows["qrl_48a61c8a441143f6"]["corrected_lesson_type"] == "PROCESS_LESSON"
    assert rows["qrl_48a61c8a441143f6"]["prior_adjustment_retained"] is False
