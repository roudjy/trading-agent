from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_controlled_artifact_regeneration_backup_plan as plan

FROZEN = "2026-06-01T12:00:00Z"


def test_plan_hashes_existing_allowed_artifacts_and_emits_restore_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path
    artifact = repo / "research" / "run_candidates_latest.v1.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"rows":[]}', encoding="utf-8")
    monkeypatch.setattr(plan, "REPO_ROOT", repo)

    snap = plan.collect_snapshot(
        artifact_relative_paths=("research/run_candidates_latest.v1.json",),
        backup_root=repo / "logs" / "qre_controlled_artifact_regeneration" / "backups" / "x",
        generated_at_utc=FROZEN,
    )

    row = snap["artifacts_to_backup"][0]
    assert row["artifact_exists"] is True
    assert row["size_bytes"] == len('{"rows":[]}')
    assert len(row["fingerprint_sha256"]) == 64
    assert row["backup_target_path"].endswith("research__run_candidates_latest.v1.json")
    assert "Copy-Item -LiteralPath" in row["restore_command_preview"]
    assert row["protected_path_classification"] == "allowed_mutable_research_artifact"
    assert row["safe_to_backup"] is True
    assert snap["safe_to_execute"] is False
    assert snap["read_only"] is True


def test_missing_artifacts_are_planned_but_warned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(plan, "REPO_ROOT", tmp_path)

    snap = plan.collect_snapshot(
        artifact_relative_paths=("research/run_candidates_latest.v1.json",),
        generated_at_utc=FROZEN,
    )

    row = snap["artifacts_to_backup"][0]
    assert row["artifact_exists"] is False
    assert row["fingerprint_sha256"] is None
    assert row["safe_to_backup"] is True
    assert "missing_artifact:research/run_candidates_latest.v1.json" in snap["validation_warnings"]


def test_protected_paths_are_reported_but_not_safe_to_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    matrix = tmp_path / "research" / "strategy_matrix.csv"
    matrix.parent.mkdir(parents=True)
    matrix.write_text("a,b\n", encoding="utf-8")
    monkeypatch.setattr(plan, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(plan, "BLOCKED_REFERENCE_PATHS", ("research/strategy_matrix.csv",))

    snap = plan.collect_snapshot(
        artifact_relative_paths=("research/run_candidates_latest.v1.json",),
        generated_at_utc=FROZEN,
    )

    blocked = snap["blocked_paths"][0]
    assert blocked["artifact_exists"] is True
    assert blocked["safe_to_backup"] is False
    assert blocked["protected_path_classification"] == "blocked_protected_runtime_or_authority_path"
    assert "blocked_existing_path:research/strategy_matrix.csv" in snap["validation_warnings"]
    assert snap["final_recommendation"] == "backup_plan_ready_with_protected_paths_blocked"


def test_write_outputs_only_allows_backup_plan_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_controlled_artifact_regeneration_backup_plan"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(plan, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(plan, "ARTIFACT_LATEST", latest)

    snap = plan.collect_snapshot(artifact_relative_paths=(), generated_at_utc=FROZEN)

    assert plan.write_outputs(snap) == latest
    parsed = json.loads(latest.read_text(encoding="utf-8"))
    assert parsed["report_kind"] == plan.REPORT_KIND
    with pytest.raises(ValueError):
        plan.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_cli_no_write_does_not_write_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_controlled_artifact_regeneration_backup_plan"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(plan, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(plan, "ARTIFACT_LATEST", latest)

    rc = plan.main(["--no-write", "--frozen-utc", FROZEN, "--indent", "0"])

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["safe_to_execute"] is False


def test_source_has_no_runtime_launch_or_mutating_queue_calls() -> None:
    src = Path(plan.__file__).read_text(encoding="utf-8")
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
