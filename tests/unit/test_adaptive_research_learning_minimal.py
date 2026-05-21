"""Tests for ``reporting.adaptive_research_learning_minimal``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import adaptive_research_learning_minimal as arl


def _r(
    *,
    campaign_id: str,
    strategy_id: str = "trend_pullback",
    behavior_family: str = "trend",
    outcome: str = "completed_no_survivor",
    near_pass: bool = False,
    regime_label: str = "neutral",
    robustness_pass: bool = False,
    evidence_count: int = 3,
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "strategy_id": strategy_id,
        "behavior_family": behavior_family,
        "outcome": outcome,
        "near_pass": near_pass,
        "regime_label": regime_label,
        "robustness_pass": robustness_pass,
        "evidence_count": evidence_count,
    }


def test_closed_vocabularies_are_pinned() -> None:
    assert arl.OUTCOMES == (
        "completed_with_candidates",
        "completed_no_survivor",
        "research_rejection",
        "degenerate_no_survivors",
        "technical_failure",
    )
    assert arl.LEARNING_ACTIONS == (
        "prioritize_research_context",
        "maintain_watch",
        "suppress_redundant_exploration",
        "review_technical_quality",
    )


def test_schema_keys_are_pinned() -> None:
    assert arl.INPUT_FEEDBACK_KEYS == (
        "campaign_id",
        "strategy_id",
        "behavior_family",
        "outcome",
        "near_pass",
        "regime_label",
        "robustness_pass",
        "evidence_count",
    )
    assert arl.STRATEGY_METRIC_KEYS == (
        "strategy_id",
        "campaign_count",
        "survivor_count",
        "near_pass_count",
        "technical_failure_count",
        "robustness_pass_count",
        "evidence_count",
        "survivor_rate",
        "near_pass_rate",
        "technical_failure_rate",
        "robustness_pass_rate",
        "evidence_coverage",
        "fitness_score",
        "learning_action",
        "regime_context",
    )


def test_feedback_must_be_list_or_tuple() -> None:
    with pytest.raises(ValueError, match="list/tuple"):
        arl.validate_feedback({"campaign_id": "x"})  # type: ignore[arg-type]


def test_too_many_feedback_records_rejected() -> None:
    records = [
        _r(campaign_id=f"c_{i:04d}")
        for i in range(arl.MAX_FEEDBACK_RECORDS + 1)
    ]
    with pytest.raises(ValueError, match="too many"):
        arl.validate_feedback(records)


def test_missing_field_rejected() -> None:
    bad = _r(campaign_id="c1")
    del bad["outcome"]
    with pytest.raises(ValueError, match="missing fields"):
        arl.validate_feedback([bad])


def test_unknown_outcome_rejected() -> None:
    with pytest.raises(ValueError, match="closed vocab"):
        arl.validate_feedback([_r(campaign_id="c1", outcome="made_up")])


def test_duplicate_campaign_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        arl.validate_feedback([_r(campaign_id="c1"), _r(campaign_id="c1")])


def test_boolean_fields_are_required() -> None:
    bad = _r(campaign_id="c1")
    bad["near_pass"] = "true"
    with pytest.raises(ValueError, match="near_pass"):
        arl.validate_feedback([bad])


def test_empty_snapshot_is_read_only_and_safe() -> None:
    snap = arl.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["safe_to_execute"] is False
    assert snap["learning_effect"] == "advisory_read_only"
    assert snap["no_policy_mutation"] is True
    assert snap["no_strategy_mutation"] is True
    assert snap["no_execution_authority"] is True
    assert snap["final_recommendation"] == "nothing_to_learn"


def test_strategy_feedback_metrics_are_deterministic() -> None:
    records = [
        _r(
            campaign_id="c1",
            outcome="completed_with_candidates",
            near_pass=True,
            regime_label="trend",
            robustness_pass=True,
            evidence_count=6,
        ),
        _r(
            campaign_id="c2",
            outcome="completed_no_survivor",
            near_pass=True,
            regime_label="trend",
            robustness_pass=False,
            evidence_count=3,
        ),
        _r(
            campaign_id="c3",
            outcome="technical_failure",
            near_pass=False,
            regime_label="chop",
            robustness_pass=False,
            evidence_count=0,
        ),
    ]
    snap = arl.collect_snapshot(records, frozen_utc="2026-05-21T00:00:00Z")
    metric = snap["strategy_metrics"][0]
    assert metric["campaign_count"] == 3
    assert metric["survivor_count"] == 1
    assert metric["near_pass_count"] == 2
    assert metric["technical_failure_count"] == 1
    assert metric["robustness_pass_count"] == 1
    assert metric["evidence_count"] == 9
    assert metric["survivor_rate"] == pytest.approx(0.333333)
    assert metric["near_pass_rate"] == pytest.approx(0.666667)
    assert metric["technical_failure_rate"] == pytest.approx(0.333333)
    assert metric["robustness_pass_rate"] == pytest.approx(0.333333)
    assert metric["evidence_coverage"] == pytest.approx(1.0)
    assert metric["fitness_score"] == pytest.approx(0.433333)
    assert metric["regime_context"] == {"chop": 1, "trend": 2}


def test_learning_actions_are_bounded() -> None:
    records = [
        _r(
            campaign_id="good1",
            strategy_id="good",
            outcome="completed_with_candidates",
            near_pass=True,
            robustness_pass=True,
            evidence_count=6,
        ),
        _r(
            campaign_id="good2",
            strategy_id="good",
            outcome="completed_with_candidates",
            near_pass=True,
            robustness_pass=True,
            evidence_count=6,
        ),
        _r(campaign_id="weak1", strategy_id="weak", evidence_count=0),
        _r(campaign_id="weak2", strategy_id="weak", evidence_count=0),
        _r(
            campaign_id="tech1",
            strategy_id="tech",
            outcome="technical_failure",
            evidence_count=0,
        ),
        _r(
            campaign_id="tech2",
            strategy_id="tech",
            outcome="technical_failure",
            evidence_count=0,
        ),
    ]
    snap = arl.collect_snapshot(records, frozen_utc="2026-05-21T00:00:00Z")
    by_strategy = {
        row["strategy_id"]: row["learning_action"]
        for row in snap["strategy_metrics"]
    }
    assert by_strategy["good"] == "prioritize_research_context"
    assert by_strategy["weak"] == "suppress_redundant_exploration"
    assert by_strategy["tech"] == "review_technical_quality"
    assert set(by_strategy.values()) <= set(arl.LEARNING_ACTIONS)


def test_behavior_family_groups_are_read_only_context() -> None:
    snap = arl.collect_snapshot(
        [
            _r(campaign_id="c1", strategy_id="s1", behavior_family="trend"),
            _r(
                campaign_id="c2",
                strategy_id="s2",
                behavior_family="trend",
                outcome="completed_with_candidates",
            ),
            _r(campaign_id="c3", strategy_id="s3", behavior_family="breakout"),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert snap["behavior_family_groups"] == {
        "breakout": {
            "campaign_count": 1,
            "strategy_ids": ["s3"],
            "survivor_count": 0,
            "survivor_rate": 0.0,
        },
        "trend": {
            "campaign_count": 2,
            "strategy_ids": ["s1", "s2"],
            "survivor_count": 1,
            "survivor_rate": 0.5,
        },
    }


def test_strategy_metrics_sort_by_fitness_desc_then_id() -> None:
    snap = arl.collect_snapshot(
        [
            _r(
                campaign_id="c1",
                strategy_id="b",
                outcome="completed_with_candidates",
                near_pass=True,
                robustness_pass=True,
                evidence_count=6,
            ),
            _r(campaign_id="c2", strategy_id="a", evidence_count=0),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert [row["strategy_id"] for row in snap["strategy_metrics"]] == [
        "b",
        "a",
    ]


def test_snapshot_is_byte_deterministic_with_frozen_timestamp() -> None:
    records = [
        _r(campaign_id="c1", evidence_count=3),
        _r(campaign_id="c2", strategy_id="s2", evidence_count=1),
    ]
    a = arl.collect_snapshot(records, frozen_utc="2026-05-21T00:00:00Z")
    b = arl.collect_snapshot(records, frozen_utc="2026-05-21T00:00:00Z")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_outputs_into_allowlisted_path(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "adaptive_research_learning_minimal"
    snap = arl.collect_snapshot(
        [_r(campaign_id="c1")],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    out = arl.write_outputs(snap, artifact_dir=base)
    assert (base / "latest.json").is_file()
    assert "adaptive_research_learning_minimal" in out["latest"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside allowlist"):
        arl._validate_write_target(tmp_path / "evil" / "latest.json")


def test_cli_status_returns_not_available(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        arl,
        "ARTIFACT_LATEST",
        tmp_path
        / "logs"
        / "adaptive_research_learning_minimal"
        / "latest.json",
    )
    rc = arl.main(["--status"])
    parsed = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert parsed["final_recommendation"] == "not_available"


def test_cli_no_write_does_not_write(capsys: pytest.CaptureFixture[str]) -> None:
    rc = arl.main(["--no-write", "--frozen-utc", "2026-05-21T00:00:00Z"])
    parsed = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert parsed["counts"]["campaign_feedback_records"] == 0
    assert parsed["safe_to_execute"] is False


def test_module_is_stdlib_only_in_source() -> None:
    src = Path(arl.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
    )
    for needle in forbidden:
        assert needle not in src


def test_module_does_not_import_execution_surfaces() -> None:
    src = Path(arl.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "agent.execution",
        "agent.risk",
        "automation.live",
        "automation.broker",
        "broker.",
        "execution.live",
        "live.",
        "paper.",
        "shadow.",
        "trading.",
    )
    for needle in forbidden:
        assert needle not in src
