from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_market_observation_hypothesis_readiness as readiness

FROZEN = "2026-06-01T12:00:00Z"


def _observation(**overrides) -> dict:
    base = {
        "observation_id": "qre-obs-fixture-001",
        "source_artifact": "fixture.json",
        "observation_type": "exit_failure_pattern",
        "asset_scope": ["BTC-EUR"],
        "timeframe_scope": ["1h"],
        "summary": "Exit rules appear to degrade the trend edge.",
        "supporting_evidence_refs": ["fixture#1"],
        "executable_hypothesis_id": "trend_pullback_v1",
        "strategy_family": "trend_pullback",
        "strategy_template_id": "trend_pullback_v1",
        "preset_name": "trend_pullback_crypto_1h",
    }
    base.update(overrides)
    return base


def _write_observations(path: Path, observations: list, **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "report_kind": "qre_market_observation_snapshot",
        "generated_at_utc": FROZEN,
        "observations": observations,
        "safe_to_execute": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_ready_observation_classifies_hypothesis_ready(tmp_path: Path) -> None:
    source = _write_observations(tmp_path / "observations.json", [_observation()])

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["counts"]["total_observations"] == 1
    assert snap["by_readiness_class"]["hypothesis_ready"] == 1
    assert snap["readiness_rows"][0]["readiness_class"] == "hypothesis_ready"
    assert snap["bridge_field_counts"]["executable_hypothesis_id"] == 1
    assert snap["safe_to_execute"] is False
    assert snap["read_only"] is True


def test_missing_executable_hypothesis_id_fails_closed(tmp_path: Path) -> None:
    source = _write_observations(
        tmp_path / "observations.json",
        [_observation(executable_hypothesis_id="")],
    )

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["by_readiness_class"]["execution_identity_missing"] == 1
    assert snap["final_recommendation"] == "explicit_executable_hypothesis_identity_required"
    assert snap["recommended_next_action"] == (
        "add_explicit_executable_hypothesis_id_to_upstream_source"
    )


def test_missing_strategy_or_preset_identity_reports_identity_missing(tmp_path: Path) -> None:
    source = _write_observations(
        tmp_path / "observations.json",
        [_observation(strategy_template_id="", preset_name="")],
    )

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["by_readiness_class"]["identity_missing"] == 1
    assert "has_strategy_template_id" in snap["readiness_rows"][0]["reason_codes"]
    assert "has_preset_name" in snap["readiness_rows"][0]["reason_codes"]


def test_missing_market_context_reports_insufficient_market_context(tmp_path: Path) -> None:
    source = _write_observations(
        tmp_path / "observations.json",
        [
            _observation(
                asset_scope=["unknown"],
                timeframe_scope=["unknown"],
                summary="",
            )
        ],
    )

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["by_readiness_class"]["insufficient_market_context"] == 1
    assert set(snap["readiness_rows"][0]["reason_codes"]) >= {
        "has_asset_or_symbol",
        "has_timeframe_or_interval",
        "bounded_text_available",
    }


def test_missing_evidence_refs_reports_insufficient_evidence_refs(tmp_path: Path) -> None:
    source = _write_observations(
        tmp_path / "observations.json",
        [_observation(supporting_evidence_refs=[])],
    )

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["by_readiness_class"]["insufficient_evidence_refs"] == 1


def test_unsupported_schema_and_malformed_rows_fail_closed(tmp_path: Path) -> None:
    source = _write_observations(
        tmp_path / "observations.json",
        [
            _observation(observation_id="", observation_type=""),
            "not-a-row",
        ],
    )

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["by_readiness_class"]["unsupported_observation_schema"] == 1
    assert snap["by_readiness_class"]["malformed_observation"] == 1
    assert snap["counts"]["not_ready"] == 2


def test_examples_are_bounded_to_twenty(tmp_path: Path) -> None:
    observations = [
        _observation(observation_id=f"qre-obs-fixture-{index:03d}") for index in range(25)
    ]
    source = _write_observations(tmp_path / "observations.json", observations)

    snap = readiness.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert len(snap["examples"]) == 20
    assert snap["counts"]["total_observations"] == 25


def test_missing_and_malformed_inputs_fail_closed(tmp_path: Path) -> None:
    missing = readiness.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    malformed = readiness.collect_snapshot(
        input_artifact_path=malformed_path,
        generated_at_utc=FROZEN,
    )

    assert readiness.NOTE_INPUT_ABSENT in missing["validation_warnings"]
    assert readiness.NOTE_INPUT_UNPARSEABLE in malformed["validation_warnings"]
    assert missing["safe_to_execute"] is False
    assert malformed["safe_to_execute"] is False


def test_cli_no_write_does_not_write_artifact(monkeypatch, tmp_path: Path, capsys) -> None:
    source = _write_observations(tmp_path / "observations.json", [_observation()])
    artifact_dir = tmp_path / "logs" / "qre_market_observation_hypothesis_readiness"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(readiness, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(readiness, "ARTIFACT_LATEST", latest)

    rc = readiness.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == readiness.REPORT_KIND


def test_write_outputs_only_allows_readiness_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_market_observation_hypothesis_readiness"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(readiness, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(readiness, "ARTIFACT_LATEST", latest)
    snap = readiness.collect_snapshot(
        input_artifact_path=_write_observations(tmp_path / "observations.json", [_observation()]),
        generated_at_utc=FROZEN,
    )

    assert readiness.write_outputs(snap) == latest
    assert latest.exists()
    with pytest.raises(ValueError):
        readiness.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_source_has_no_forbidden_calls_or_writes() -> None:
    src = Path(readiness.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "os.system",
        "os.popen",
        "shell=True",
        "research.run_research",
        "strategy_matrix.csv",
        "research/research_latest.json",
        "seed.jsonl",
        "generated_seed.jsonl",
        "campaigns/",
        "paper/",
        "shadow/",
        "live/",
        "SequenceMatcher",
        "difflib",
        "fuzzy",
    )
    for token in forbidden:
        assert token not in src, token
