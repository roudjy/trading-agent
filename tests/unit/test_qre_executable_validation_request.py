from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from reporting import qre_executable_validation_request as req

FROZEN = "2026-06-01T12:00:00Z"


@dataclass(frozen=True)
class PresetFixture:
    name: str = "trend_pullback_crypto_1h"
    hypothesis_id: str | None = "trend_pullback_v1"
    enabled: bool = True
    diagnostic_only: bool = False
    excluded_from_candidate_promotion: bool = False
    timeframe: str = "1h"
    universe: tuple[str, ...] = ("BTC-EUR",)
    bundle: tuple[str, ...] = ("trend_pullback_v1",)


def _hypothesis(**overrides) -> dict:
    base = {
        "hypothesis_id": "qre-hyp-fixture",
        "source_observation_id": "qre-obs-fixture",
        "executable_hypothesis_id": "trend_pullback_v1",
        "source_hypothesis_id": "source-trend-pullback",
        "validation_plan_id": "qre-plan-fixture",
        "run_manifest_id": "qre-run-fixture",
        "preset_name": "trend_pullback_crypto_1h",
        "strategy_family": "trend_pullback",
        "strategy_template_id": "trend_pullback_v1",
        "asset_scope": ["BTC-EUR"],
        "timeframe_scope": ["1h"],
        "supporting_evidence_refs": ["fixture#1"],
    }
    base.update(overrides)
    return base


def _write_hypotheses(path: Path, hypotheses: list) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": "qre_hypothesis_candidates",
                "generated_at_utc": FROZEN,
                "hypotheses": hypotheses,
                "safe_to_execute": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _write_readiness(path: Path, readiness_class: str = "hypothesis_ready") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": "qre_market_observation_hypothesis_readiness",
                "generated_at_utc": FROZEN,
                "readiness_rows": [
                    {
                        "observation_id": "qre-obs-fixture",
                        "readiness_class": readiness_class,
                        "reason_codes": [],
                    }
                ],
                "safe_to_execute": False,
                "read_only": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_ready_request_requires_operator_review_and_has_descriptive_preview(
    tmp_path: Path,
) -> None:
    source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    readiness = _write_readiness(tmp_path / "readiness.json")

    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    row = snap["validation_requests"][0]
    assert row["request_status"] == "request_ready_for_operator_review"
    assert row["allowed_command_preview"].startswith("Operator-reviewed validation request")
    assert row["safe_to_execute"] is False
    assert row["requires_operator_approval"] is True
    assert snap["counts"]["ready"] == 1
    assert snap["safe_to_execute"] is False


def test_missing_executable_hypothesis_id_blocks_request(tmp_path: Path) -> None:
    source = _write_hypotheses(
        tmp_path / "hypotheses.json",
        [_hypothesis(executable_hypothesis_id="")],
    )
    readiness = _write_readiness(tmp_path / "readiness.json")

    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    row = snap["validation_requests"][0]
    assert row["request_status"] == "request_blocked_identity_missing"
    assert row["allowed_command_preview"] is None


def test_preset_ineligible_blocks_request(tmp_path: Path) -> None:
    source = _write_hypotheses(
        tmp_path / "hypotheses.json",
        [_hypothesis(strategy_template_id="breakout_momentum")],
    )
    readiness = _write_readiness(tmp_path / "readiness.json")

    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    row = snap["validation_requests"][0]
    assert row["request_status"] == "request_blocked_preset_ineligible"
    assert row["eligibility_status"] == "strategy_template_not_in_bundle"


def test_market_context_not_ready_blocks_request(tmp_path: Path) -> None:
    source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    readiness = _write_readiness(tmp_path / "readiness.json", "execution_identity_missing")

    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    assert snap["validation_requests"][0]["request_status"] == (
        "request_blocked_market_context_missing"
    )


def test_missing_validation_plan_or_run_manifest_blocks_request(tmp_path: Path) -> None:
    readiness = _write_readiness(tmp_path / "readiness.json")
    no_plan = _write_hypotheses(
        tmp_path / "no-plan.json",
        [_hypothesis(validation_plan_id="")],
    )
    no_manifest = _write_hypotheses(
        tmp_path / "no-manifest.json",
        [_hypothesis(run_manifest_id="")],
    )

    plan_snap = req.collect_snapshot(
        input_artifact_path=no_plan,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )
    manifest_snap = req.collect_snapshot(
        input_artifact_path=no_manifest,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    assert plan_snap["validation_requests"][0]["request_status"] == (
        "request_blocked_validation_plan_missing"
    )
    assert manifest_snap["validation_requests"][0]["request_status"] == (
        "request_blocked_run_manifest_missing"
    )


def test_malformed_candidate_row_fails_closed(tmp_path: Path) -> None:
    source = _write_hypotheses(tmp_path / "hypotheses.json", ["not-a-row"])
    readiness = _write_readiness(tmp_path / "readiness.json")

    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    assert snap["validation_requests"][0]["request_status"] == "request_malformed"
    assert snap["validation_requests"][0]["safe_to_execute"] is False


def test_missing_and_malformed_inputs_fail_closed(tmp_path: Path) -> None:
    missing = req.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    malformed = req.collect_snapshot(
        input_artifact_path=malformed_path,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    assert req.NOTE_INPUT_ABSENT in missing["validation_warnings"]
    assert req.NOTE_INPUT_UNPARSEABLE in malformed["validation_warnings"]
    assert missing["safe_to_execute"] is False
    assert malformed["safe_to_execute"] is False


def test_collects_readiness_directly_when_readiness_artifact_absent(tmp_path: Path) -> None:
    source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    market_observations = tmp_path / "observations.json"
    market_observations.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": "qre_market_observation_snapshot",
                "observations": [
                    {
                        "observation_id": "qre-obs-fixture",
                        "source_artifact": "fixture.json",
                        "observation_type": "exit_failure_pattern",
                        "asset_scope": ["BTC-EUR"],
                        "timeframe_scope": ["1h"],
                        "summary": "Ready.",
                        "supporting_evidence_refs": ["fixture#1"],
                        "executable_hypothesis_id": "trend_pullback_v1",
                        "strategy_family": "trend_pullback",
                        "strategy_template_id": "trend_pullback_v1",
                        "preset_name": "trend_pullback_crypto_1h",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=tmp_path / "missing-readiness.json",
        market_observation_artifact_path=market_observations,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    assert snap["validation_requests"][0]["request_status"] == ("request_ready_for_operator_review")


def test_cli_no_write_does_not_write_artifact(monkeypatch, tmp_path: Path, capsys) -> None:
    source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    readiness = _write_readiness(tmp_path / "readiness.json")
    artifact_dir = tmp_path / "logs" / "qre_executable_validation_request"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(req, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(req, "ARTIFACT_LATEST", latest)

    rc = req.main(
        [
            "--no-write",
            "--source",
            str(source),
            "--readiness-source",
            str(readiness),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == req.REPORT_KIND


def test_write_outputs_only_allows_request_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_executable_validation_request"
    latest = artifact_dir / "latest.json"
    source = _write_hypotheses(tmp_path / "hypotheses.json", [_hypothesis()])
    readiness = _write_readiness(tmp_path / "readiness.json")
    monkeypatch.setattr(req, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(req, "ARTIFACT_LATEST", latest)
    snap = req.collect_snapshot(
        input_artifact_path=source,
        readiness_artifact_path=readiness,
        generated_at_utc=FROZEN,
        presets=[PresetFixture()],
    )

    assert req.write_outputs(snap) == latest
    assert latest.exists()
    with pytest.raises(ValueError):
        req.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_source_has_no_forbidden_calls_or_writes() -> None:
    src = Path(req.__file__).read_text(encoding="utf-8")
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
