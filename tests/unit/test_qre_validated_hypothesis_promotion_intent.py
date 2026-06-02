from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_validated_hypothesis_promotion_intent as promotion


FROZEN = "2026-06-01T12:00:00Z"


def _write_payload(path: Path, report_kind: str, field: str, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": report_kind,
                "generated_at_utc": FROZEN,
                field: rows,
                "safe_to_execute": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _quality_row(**overrides) -> dict:
    base = {
        "hypothesis_id": "qre-hyp-fixture-001",
        "evidence_update_id": "qre-evidence-fixture-001",
        "result_id": "qre-result-fixture-001",
        "quality_class": "usable",
        "evidence_decision": "supported",
        "validation_status": "passed",
        "promotion_allowed": True,
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _artifact_set(tmp_path: Path, *, quality_rows: list[dict] | None = None) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return {
        "hypotheses": _write_payload(
            tmp_path / "hypotheses.json",
            "qre_hypothesis_candidates",
            "hypotheses",
            [{"hypothesis_id": "qre-hyp-fixture-001", "safe_to_execute": False}],
        ),
        "results": _write_payload(
            tmp_path / "results.json",
            "qre_hypothesis_validation_results",
            "validation_results",
            [{"result_id": "qre-result-fixture-001", "safe_to_execute": False}],
        ),
        "updates": _write_payload(
            tmp_path / "updates.json",
            "qre_hypothesis_evidence_update",
            "evidence_updates",
            [{"evidence_update_id": "qre-evidence-fixture-001", "safe_to_execute": False}],
        ),
        "quality": _write_payload(
            tmp_path / "quality.json",
            "qre_evidence_quality_gate",
            "evidence_quality_rows",
            [_quality_row()] if quality_rows is None else quality_rows,
        ),
    }


def _collect(paths: dict[str, Path]) -> dict:
    return promotion.collect_snapshot(
        hypotheses_path=paths["hypotheses"],
        validation_results_path=paths["results"],
        evidence_updates_path=paths["updates"],
        evidence_quality_path=paths["quality"],
        generated_at_utc=FROZEN,
    )


def _assert_safety_flags_false(snapshot: dict) -> None:
    for key in (
        "safe_to_execute",
        "writes_development_work_queue",
        "writes_seed_jsonl",
        "writes_generated_seed_jsonl",
        "writes_research_action_queue",
        "mutates_campaign_queue",
        "mutates_strategy_or_preset",
        "mutates_paper_shadow_live_runtime",
        "launches_codex",
        "eligible_for_direct_execution",
    ):
        assert snapshot[key] is False


def _assert_intent_is_never_executable(intent: dict) -> None:
    assert intent["actual_writes_enabled"] is False
    assert intent["operator_approval_required"] is True
    assert intent["safe_to_execute"] is False
    assert intent["eligible_for_direct_execution"] is False
    assert intent["writes_development_work_queue"] is False
    assert intent["writes_research_action_queue"] is False
    assert intent["writes_generated_seed_jsonl"] is False
    assert intent["mutates_campaign_queue"] is False
    assert intent["mutates_strategy_or_preset"] is False
    assert intent["mutates_paper_shadow_live_runtime"] is False


def test_missing_evidence_quality_gate_fails_closed_with_zero_ready_intents(
    tmp_path: Path,
) -> None:
    paths = _artifact_set(tmp_path)
    paths["quality"] = tmp_path / "missing-quality.json"

    snap = _collect(paths)

    assert snap["promotion_intents"] == []
    assert snap["counts"]["ready_for_operator_review"] == 0
    assert promotion.NOTE_INPUT_ISSUES in snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_usable_supported_hypothesis_produces_operator_review_intent(
    tmp_path: Path,
) -> None:
    snap = _collect(_artifact_set(tmp_path, quality_rows=[_quality_row(quality_class="usable")]))

    intent = snap["promotion_intents"][0]
    assert intent["intent_status"] == "operator_review_required"
    assert intent["promotion_target"] == "qre_research_action_proposal_intake_candidate"
    assert intent["promotion_intent_id"].startswith("qre-promotion-")
    _assert_intent_is_never_executable(intent)


def test_strong_supported_hypothesis_requires_review_and_is_not_auto_executable(
    tmp_path: Path,
) -> None:
    snap = _collect(_artifact_set(tmp_path, quality_rows=[_quality_row(quality_class="strong")]))

    intent = snap["promotion_intents"][0]
    assert intent["intent_status"] == "operator_review_required"
    assert intent["promotion_target"] == "development_queue_candidate"
    assert intent["safe_to_execute"] is False
    assert intent["eligible_for_direct_execution"] is False
    assert intent["actual_writes_enabled"] is False


@pytest.mark.parametrize(
    ("quality_class", "evidence_decision", "expected_status"),
    [
        ("thin", "supported", "not_ready"),
        ("insufficient", "supported", "not_ready"),
        ("contradictory", "contradiction_detected", "blocked"),
        ("contradictory", "falsified", "blocked"),
    ],
)
def test_unready_or_falsified_quality_rows_do_not_create_ready_intents(
    tmp_path: Path,
    quality_class: str,
    evidence_decision: str,
    expected_status: str,
) -> None:
    row = _quality_row(
        quality_class=quality_class,
        evidence_decision=evidence_decision,
        promotion_allowed=False,
    )

    intent = _collect(_artifact_set(tmp_path, quality_rows=[row]))["promotion_intents"][0]

    assert intent["intent_status"] == expected_status
    assert intent["promotion_target"] == "none"
    assert intent["actual_writes_enabled"] is False


def test_intent_lanes_model_all_future_mutation_lanes_as_intent_only(
    tmp_path: Path,
) -> None:
    intent = _collect(_artifact_set(tmp_path))["promotion_intents"][0]

    assert set(intent["intent_lanes"]) == {
        "research_action_queue_intent",
        "generated_seed_intent",
        "strategy_or_preset_intent",
        "campaign_intent",
    }
    for lane in intent["intent_lanes"].values():
        assert lane["operator_approval_required"] is True
        assert lane["actual_writes_enabled"] is False
        assert lane["safe_to_execute"] is False
        assert lane["eligible_for_direct_execution"] is False


def test_forbidden_actions_include_required_mutation_categories(tmp_path: Path) -> None:
    intent = _collect(_artifact_set(tmp_path))["promotion_intents"][0]
    forbidden = set(intent["forbidden_actions"])

    assert "actual_research_action_queue_write_forbidden" in forbidden
    assert "generated_seed_write_forbidden" in forbidden
    assert "campaign_queue_mutation_forbidden" in forbidden
    assert "strategy_or_preset_mutation_forbidden" in forbidden
    assert "paper_shadow_live_activation_forbidden" in forbidden
    assert "broker_risk_execution_change_forbidden" in forbidden
    assert "codex_launch_forbidden" in forbidden
    assert "branch_pr_automation_forbidden" in forbidden


def test_deterministic_promotion_intent_id(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)

    snap_a = _collect(paths)
    snap_b = _collect(paths)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    assert snap_a["promotion_intents"][0]["promotion_intent_id"] == snap_b["promotion_intents"][0][
        "promotion_intent_id"
    ]


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    paths = _artifact_set(tmp_path)
    artifact_dir = tmp_path / "logs" / "qre_validated_hypothesis_promotion_intent"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(promotion, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(promotion, "ARTIFACT_LATEST", latest)

    rc = promotion.main(
        [
            "--no-write",
            "--hypotheses-source",
            str(paths["hypotheses"]),
            "--results-source",
            str(paths["results"]),
            "--evidence-updates-source",
            str(paths["updates"]),
            "--evidence-quality-source",
            str(paths["quality"]),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["promotion_intents"][0]["intent_status"] == "operator_review_required"


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        promotion._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(promotion.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token


def test_source_does_not_write_active_or_mutating_paths() -> None:
    src = Path(promotion.__file__).read_text(encoding="utf-8")
    forbidden = (
        "seed.jsonl",
        "delegation_seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "campaigns/",
        "agent/backtesting/strategies.py",
        "registry.py",
        "paper/",
        "shadow/",
        "live/",
    )
    for token in forbidden:
        assert token not in src, token


def test_all_top_level_mutation_flags_are_false(tmp_path: Path) -> None:
    snap = _collect(_artifact_set(tmp_path))

    _assert_safety_flags_false(snap)
    _assert_intent_is_never_executable(snap["promotion_intents"][0])
