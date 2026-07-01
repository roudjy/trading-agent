from __future__ import annotations

from pathlib import Path

from packages.qre_research import hypothesis_lifecycle as lifecycle


def test_failure_actions_snapshot_marks_canonical_next_action_actionable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        lifecycle,
        "build_feasibility_snapshot",
        lambda **_: {
            "rows": [
                {
                    "thesis_id": "qhc_1",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                    "missing_prerequisites": [],
                }
            ]
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "build_sampling_snapshot",
        lambda **_: {
            "rows": [
                {
                    "thesis_id": "qhc_1",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                    "sampling_reason_codes": [],
                    "next_action": "evaluate_exact_blocker_or_empirical_campaign_gap",
                }
            ]
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "_read_empirical_pack",
        lambda _repo_root: {
            "source_hypothesis_id": "cross_sectional_momentum_v0",
            "recommended_next_action": "launch_data_oos_capacity_expansion",
            "active_blockers": ["REQUEST_MORE_EVIDENCE"],
        },
    )

    snapshot = lifecycle.build_failure_actions_snapshot(repo_root=tmp_path)

    row = snapshot["rows"][0]
    assert row["next_action"] == "launch_data_oos_capacity_expansion"
    assert row["actionable"] is True
    assert row["failure_codes"] == ["REQUEST_MORE_EVIDENCE"]
    assert snapshot["summary"]["actionable_failure_count"] == 1
