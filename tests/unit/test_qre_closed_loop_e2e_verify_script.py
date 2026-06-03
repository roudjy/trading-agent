from __future__ import annotations

from pathlib import Path

SCRIPT = Path("scripts/qre_closed_loop_e2e_verify.ps1")


def test_qre_closed_loop_e2e_verify_script_exists_and_uses_safe_sequence() -> None:
    assert SCRIPT.exists()
    src = SCRIPT.read_text(encoding="utf-8")
    expected = (
        "reporting.qre_closed_loop_materialization_runner",
        "reporting.qre_market_observation_hypothesis_readiness",
        "reporting.qre_executable_validation_request",
        "reporting.qre_validation_request_dry_run_runner",
        "reporting.qre_executable_hypothesis_identity_bridge_diagnostics",
        "reporting.qre_controlled_artifact_regeneration_backup_plan",
        "reporting.qre_controlled_artifact_regeneration_runner",
        "reporting.qre_post_run_evidence_promotion_audit",
        "reporting.qre_operator_closed_loop_report",
    )
    command_block = src[src.index('Invoke-QreCommand "Closed-loop materialization dry check"') :]
    positions = [command_block.index(item) for item in expected]
    assert positions == sorted(positions)
    assert "--dry-run" in src
    assert "--write-reporting-only" in src
    assert "--allow-research-regeneration" in src
    assert "research.run_research directly" in src


def test_qre_closed_loop_e2e_verify_script_has_no_direct_runtime_execution_calls() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "-m research.run_research",
        "Start-Job",
        "Start-Process",
        "gh pr",
        "git push",
        "generated_seed.jsonl",
        "seed.jsonl",
    )
    for token in forbidden:
        assert token not in src, token
