from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_controlled_artifact_regeneration_runner as runner

FROZEN = "2026-06-01T12:00:00Z"


def _route(_: str | None = None) -> dict:
    return {
        "executable_validation_request": {"counts": {"ready": 0}},
        "validation_request_dry_run": {"counts": {"ready": 0}},
    }


def _plan(row: dict | None = None) -> dict:
    return {
        "report_kind": "qre_controlled_artifact_regeneration_backup_plan",
        "safe_to_execute": False,
        "read_only": True,
        "artifacts_to_backup": [row] if row else [],
        "blocked_paths": [],
        "validation_warnings": [],
        "final_recommendation": "backup_plan_ready_for_controlled_regeneration",
    }


def test_default_dry_run_writes_only_runner_log_when_cli_invoked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_controlled_artifact_regeneration"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(runner, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(runner, "ARTIFACT_LATEST", latest)
    monkeypatch.setattr(runner, "BACKUP_ROOT", artifact_dir / "backups")
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner.backup_plan, "collect_snapshot", lambda **_: _plan())
    monkeypatch.setattr(runner, "_route_snapshot", lambda **_: _route())

    rc = runner.main(["--frozen-utc", FROZEN, "--indent", "0"])

    assert rc == 0
    assert latest.exists()
    assert list((artifact_dir / "backups").glob("*")) == []
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["mode"] == runner.MODE_DRY_RUN
    assert parsed["backups_created"] == []
    assert parsed["executed_research_regeneration"] is False
    assert parsed["executed_reporting_materialization"] is False


def test_write_mode_uses_backup_plan_and_copies_only_approved_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "research" / "run_candidates_latest.v1.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"rows":[]}', encoding="utf-8")
    backup_root = tmp_path / "logs" / "qre_controlled_artifact_regeneration" / "backups"
    row = {
        "artifact_path": "research/run_candidates_latest.v1.json",
        "artifact_exists": True,
        "safe_to_backup": True,
        "restore_command_preview": "preview",
    }
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(runner.backup_plan, "collect_snapshot", lambda **_: _plan(row))
    monkeypatch.setattr(runner, "_route_snapshot", lambda **_: _route())
    monkeypatch.setattr(
        runner,
        "_write_reporting_materialization",
        lambda generated_at_utc: {"executed": True, "artifact_path": "logs/qre_x/latest.json"},
    )

    snap = runner.collect_snapshot(
        dry_run=False,
        write_reporting_only=True,
        generated_at_utc=FROZEN,
    )

    assert snap["mode"] == runner.MODE_WRITE_REPORTING_ONLY
    assert snap["backup_dir"] is not None
    assert snap["backups_created"][0]["artifact_path"] == "research/run_candidates_latest.v1.json"
    assert (backup_root / "20260601T120000" / "research__run_candidates_latest.v1.json").exists()
    assert snap["executed_reporting_materialization"] is True


def test_missing_and_protected_plan_rows_are_not_copied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backup_root = tmp_path / "logs" / "qre_controlled_artifact_regeneration" / "backups"
    missing = {
        "artifact_path": "research/missing.json",
        "artifact_exists": False,
        "safe_to_backup": True,
    }
    protected = {
        "artifact_path": "research/strategy_matrix.csv",
        "artifact_exists": True,
        "safe_to_backup": False,
    }
    plan_snapshot = _plan()
    plan_snapshot["artifacts_to_backup"] = [missing, protected]
    plan_snapshot["blocked_paths"] = [protected]
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(runner.backup_plan, "collect_snapshot", lambda **_: plan_snapshot)
    monkeypatch.setattr(runner, "_route_snapshot", lambda **_: _route())
    monkeypatch.setattr(
        runner,
        "_write_reporting_materialization",
        lambda generated_at_utc: {"executed": True},
    )

    snap = runner.collect_snapshot(
        write_reporting_only=True, dry_run=False, generated_at_utc=FROZEN
    )

    assert snap["backups_created"] == []
    assert not list(backup_root.rglob("*.*"))


def test_allow_research_regeneration_fails_closed_after_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "research" / "run_candidates_latest.v1.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"rows":[]}', encoding="utf-8")
    row = {
        "artifact_path": "research/run_candidates_latest.v1.json",
        "artifact_exists": True,
        "safe_to_backup": True,
    }
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner, "BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(runner.backup_plan, "collect_snapshot", lambda **_: _plan(row))
    monkeypatch.setattr(runner, "_route_snapshot", lambda **_: _route())

    snap = runner.collect_snapshot(
        dry_run=False,
        allow_research_regeneration=True,
        generated_at_utc=FROZEN,
    )

    assert snap["mode"] == runner.MODE_ALLOW_RESEARCH_REGENERATION
    assert snap["backups_created"]
    assert snap["executed_research_regeneration"] is False
    assert (
        snap["research_regeneration"]["reason"]
        == "no_narrow_safe_research_regeneration_api_identified"
    )
    assert (
        snap["final_recommendation"] == "controlled_regeneration_requires_operator_manual_command"
    )


def test_restore_from_backup_emits_exact_copy_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups" / "x"
    backup_dir.mkdir(parents=True)
    (backup_dir / "research__run_candidates_latest.v1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(runner.backup_plan, "collect_snapshot", lambda **_: _plan())
    monkeypatch.setattr(runner, "_route_snapshot", lambda **_: _route())

    snap = runner.collect_snapshot(restore_from_backup=backup_dir, generated_at_utc=FROZEN)

    assert snap["mode"] == runner.MODE_RESTORE_FROM_BACKUP
    assert snap["restore_instructions"] == [
        "Copy-Item -LiteralPath 'backups/x/research__run_candidates_latest.v1.json' "
        "-Destination 'research/run_candidates_latest.v1.json' -Force"
    ]


def test_write_outputs_only_allows_runner_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_controlled_artifact_regeneration"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(runner, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(runner, "ARTIFACT_LATEST", latest)
    monkeypatch.setattr(runner.backup_plan, "collect_snapshot", lambda **_: _plan())
    monkeypatch.setattr(runner, "_route_snapshot", lambda **_: _route())
    snap = runner.collect_snapshot(generated_at_utc=FROZEN)

    assert runner.write_outputs(snap) == latest
    with pytest.raises(ValueError):
        runner.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_source_has_no_subprocess_or_direct_research_execution() -> None:
    src = Path(runner.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "os.system",
        "os.popen",
        "shell=True",
        "research.run_research",
        "seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "SequenceMatcher",
        "difflib",
        "fuzzy",
    )
    for token in forbidden:
        assert token not in src, token
