from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_validation_request_dry_run_runner as dry_run

FROZEN = "2026-06-01T12:00:00Z"


def _request(**overrides) -> dict:
    base = {
        "request_id": "qre-req-fixture",
        "qre_hypothesis_id": "qre-hyp-fixture",
        "executable_hypothesis_id": "trend_pullback_v1",
        "preset_name": "trend_pullback_crypto_1h",
        "strategy_template_id": "trend_pullback_v1",
        "asset": "BTC-EUR",
        "timeframe": "1h",
        "request_status": "request_ready_for_operator_review",
        "requires_operator_approval": True,
        "allowed_command_preview": "Operator-reviewed validation request for fixture",
        "safe_to_execute": False,
    }
    base.update(overrides)
    return base


def _write_requests(path: Path, requests: list) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": "qre_executable_validation_request",
                "generated_at_utc": FROZEN,
                "validation_requests": requests,
                "safe_to_execute": False,
                "read_only": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_ready_request_with_operator_approval_produces_dry_run_ready(tmp_path: Path) -> None:
    source = _write_requests(tmp_path / "requests.json", [_request(operator_approved=True)])

    snap = dry_run.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    row = snap["dry_run_results"][0]
    assert row["dry_run_status"] == "dry_run_ready"
    assert row["would_run_command_preview"].startswith("Operator-reviewed")
    assert row["would_write_artifacts"] == list(dry_run.FUTURE_OUTPUTS)
    assert row["backup_required"] is True
    assert row["safe_to_execute"] is False
    assert row["executed"] is False
    assert snap["executed_anything"] is False


def test_request_not_ready_blocks_dry_run(tmp_path: Path) -> None:
    source = _write_requests(
        tmp_path / "requests.json",
        [_request(request_status="request_blocked_identity_missing")],
    )

    snap = dry_run.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["dry_run_results"][0]["dry_run_status"] == ("dry_run_blocked_request_not_ready")


def test_missing_operator_approval_blocks_dry_run(tmp_path: Path) -> None:
    source = _write_requests(tmp_path / "requests.json", [_request()])

    snap = dry_run.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["dry_run_results"][0]["dry_run_status"] == (
        "dry_run_blocked_missing_operator_approval"
    )


def test_missing_command_preview_blocks_dry_run(tmp_path: Path) -> None:
    source = _write_requests(
        tmp_path / "requests.json",
        [_request(operator_approved=True, allowed_command_preview="")],
    )

    snap = dry_run.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert snap["dry_run_results"][0]["dry_run_status"] == (
        "dry_run_blocked_missing_command_preview"
    )


def test_malformed_request_row_fails_closed(tmp_path: Path) -> None:
    source = _write_requests(tmp_path / "requests.json", ["not-a-row"])

    snap = dry_run.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    row = snap["dry_run_results"][0]
    assert row["dry_run_status"] == "dry_run_malformed"
    assert row["safe_to_execute"] is False
    assert row["executed"] is False


def test_missing_and_malformed_inputs_fail_closed(tmp_path: Path) -> None:
    missing = dry_run.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc=FROZEN,
    )
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    malformed = dry_run.collect_snapshot(
        input_artifact_path=malformed_path,
        generated_at_utc=FROZEN,
    )

    assert dry_run.NOTE_INPUT_ABSENT in missing["validation_warnings"]
    assert dry_run.NOTE_INPUT_UNPARSEABLE in malformed["validation_warnings"]
    assert missing["safe_to_execute"] is False
    assert malformed["safe_to_execute"] is False


def test_cli_no_write_does_not_write_artifact(monkeypatch, tmp_path: Path, capsys) -> None:
    source = _write_requests(tmp_path / "requests.json", [_request()])
    artifact_dir = tmp_path / "logs" / "qre_validation_request_dry_run"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(dry_run, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(dry_run, "ARTIFACT_LATEST", latest)

    rc = dry_run.main(
        ["--no-write", "--source", str(source), "--frozen-utc", FROZEN, "--indent", "0"]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == dry_run.REPORT_KIND


def test_write_outputs_only_allows_dry_run_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_validation_request_dry_run"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(dry_run, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(dry_run, "ARTIFACT_LATEST", latest)
    source = _write_requests(tmp_path / "requests.json", [_request()])
    snap = dry_run.collect_snapshot(input_artifact_path=source, generated_at_utc=FROZEN)

    assert dry_run.write_outputs(snap) == latest
    assert latest.exists()
    with pytest.raises(ValueError):
        dry_run.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_source_has_no_forbidden_calls_or_mutating_writes() -> None:
    src = Path(dry_run.__file__).read_text(encoding="utf-8")
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
