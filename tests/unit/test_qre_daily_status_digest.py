from __future__ import annotations

import json
from pathlib import Path

from research import qre_daily_status_digest as digest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_loop_latest(root: Path, *, protected_outputs_mutated: bool = False) -> Path:
    loop_dir = root / "loop"
    latest_path = loop_dir / "latest.json"
    _write_json(
        latest_path,
        {
            "schema_version": "1.0",
            "report_kind": "qre_autonomous_market_research_loop",
            "summary": {
                "controlled_research_inner_loop_count": 2,
                "market_intake_cycle_count": 1,
                "unsafe_actions_blocked": 0,
                "protected_outputs_mutated": protected_outputs_mutated,
            },
            "cycles": [
                {
                    "cycle_id": "cycle-1",
                    "market_intake": {"universe": ["AAPL", "MSFT"]},
                    "hypothesis_generation": {"statement": "test hypothesis"},
                    "preset_selection": {"preset_id": "trend_continuation_daily_v1"},
                    "metric_evidence": {"metric_mode": "bounded_metric_evidence"},
                    "result_analysis": {"content_blockers": ["safe_metric_runner_missing_or_cache_unavailable"]},
                    "next_action": {"recommended_action": "add_cache_only_metric_path"},
                }
            ],
        },
    )
    return latest_path


def _valid_tiingo_lifecycle_payload() -> dict:
    authority = {
        "trading_authority": False,
        "creates_candidates": False,
        "runs_screening": False,
        "promotes_candidates": False,
        "registers_strategy": False,
        "validation_authority": False,
        "paper_authority": False,
        "shadow_authority": False,
        "live_authority": False,
    }
    return {
        "report_kind": "qre_tiingo_hypothesis_lifecycle",
        "schema_version": 1,
        "summary": {
            "lifecycle_verdict": "pass_research_only_admission_boundary",
            "hypotheses_seen": 5,
            "hypotheses_generated_events": 5,
            "hypotheses_admitted": 5,
            "hypotheses_rejected": 0,
            "hypotheses_blocked": 0,
            "operator_updates_count": 10,
            "daily_digest_ready": True,
        },
        "daily_digest_input": {
            "digest_kind": "qre_hypothesis_lifecycle_daily_input",
            "counts": {
                "generated": 5,
                "admitted": 5,
                "rejected": 0,
                "blocked": 0,
            },
            "next_actions": ["materialize_research_candidate_later"],
            "authority_summary": dict(authority),
        },
        "operator_updates": [{"message": "update"} for _ in range(10)],
        "safety": dict(authority),
    }


def _write_tiingo_lifecycle(root: Path, payload: dict | None = None) -> Path:
    latest_path = root / "tiingo_lifecycle" / "latest.json"
    _write_json(latest_path, payload or _valid_tiingo_lifecycle_payload())
    return latest_path


def _valid_tiingo_candidate_loop_payload() -> dict:
    authority = {
        "research_only": True,
        "screening_only": True,
        "trading_authority": False,
        "creates_orders": False,
        "broker_authority": False,
        "risk_authority": False,
        "promotes_candidates": False,
        "registers_strategy": False,
        "validation_authority": False,
        "paper_authority": False,
        "shadow_authority": False,
        "live_authority": False,
    }
    return {
        "report_kind": "qre_tiingo_candidate_research_loop",
        "schema_version": 1,
        "source_snapshot_id": "qdsnap_test",
        "summary": {
            "loop_verdict": "pass_research_only_candidate_loop",
            "input_contracts_admitted": 5,
            "candidates_materialized": 5,
            "candidates_screened": 5,
            "screening_pass": 2,
            "screening_fail": 0,
            "null_not_beaten": 3,
            "insufficient_evidence": 0,
            "feedback_records": 5,
            "feedback_consumed": False,
            "feedback_applied_count": 0,
            "next_run_feedback_ready": True,
        },
        "evidence_ledger_summary": {
            "evidence_records": 5,
            "retain_research_evidence": 2,
            "weak_research_evidence": 3,
            "insufficient_research_evidence": 0,
            "blocked_research_evidence": 0,
            "research_only": True,
            "trading_authority": False,
        },
        "variant_summary": {
            "base_candidates": 5,
            "variant_candidates": 0,
            "variants_requested": 0,
            "variants_materialized": 0,
            "modified_by_prior_feedback": 0,
            "retained_by_prior_feedback": 0,
            "suppressed_by_prior_feedback": 0,
        },
        "daily_digest_input": {
            "digest_kind": "qre_tiingo_candidate_research_loop_daily_input",
            "authority_summary": dict(authority),
        },
        "safety": dict(authority),
    }


def _write_tiingo_candidate_loop(root: Path, payload: dict | None = None) -> Path:
    latest_path = root / "candidate_loop" / "latest.json"
    _write_json(latest_path, payload or _valid_tiingo_candidate_loop_payload())
    return latest_path


def _run_digest(root: Path, **overrides) -> dict:
    loop_latest_path = overrides.pop("loop_latest_path", None) or _write_loop_latest(root)
    kwargs = {
        "loop_latest_path": loop_latest_path,
        "build_request_latest_path": root / "loop" / "latest_build_request.json",
        "build_consumer_latest_path": root / "consumer" / "latest.json",
        "backend_results_dir": root / "consumer" / "backend_results",
        "pr_auto_merge_latest_path": root / "pr_gate" / "latest.json",
        "runtime_continuation_latest_path": root / "runtime" / "latest.json",
        "flywheel_latest_path": root / "flywheel" / "latest.json",
        "trusted_loop_review_latest_path": root / "trusted_loop" / "latest.json",
        "research_memory_current_artifacts_latest_path": root / "memory" / "latest.json",
        "shadow_readiness_latest_path": root / "shadow" / "latest.json",
        "tiingo_hypothesis_lifecycle_latest_path": root / "tiingo_lifecycle" / "latest.json",
        "tiingo_candidate_loop_latest_path": root / "candidate_loop" / "latest.json",
        "output_dir": root / "daily",
        "write": True,
    }
    kwargs.update(overrides)
    return digest.run_daily_status_digest(**kwargs)


def test_daily_digest_summarizes_many_cycles_and_build_lane(tmp_path: Path) -> None:
    loop_latest_path = _write_loop_latest(tmp_path)
    _write_json(
        tmp_path / "loop" / "build_requests" / "build-request-1.json",
        {
            "request_id": "build-request-1",
            "next_action": "add_cache_only_metric_path",
            "safe_for_ade_build": True,
        },
    )

    packet = digest.run_daily_status_digest(
        loop_latest_path=loop_latest_path,
        build_request_latest_path=tmp_path / "loop" / "latest_build_request.json",
        build_consumer_latest_path=tmp_path / "consumer" / "latest.json",
        backend_results_dir=tmp_path / "consumer" / "backend_results",
            pr_auto_merge_latest_path=tmp_path / "pr_gate" / "latest.json",
            runtime_continuation_latest_path=tmp_path / "runtime" / "latest.json",
            flywheel_latest_path=tmp_path / "flywheel" / "latest.json",
            trusted_loop_review_latest_path=tmp_path / "trusted_loop" / "latest.json",
            research_memory_current_artifacts_latest_path=tmp_path / "memory" / "latest.json",
            shadow_readiness_latest_path=tmp_path / "shadow" / "latest.json",
            output_dir=tmp_path / "daily",
            write=True,
        )

    assert packet["summary"]["autonomous_cycles"] == 1
    assert packet["summary"]["market_intake_cycles"] == 1
    assert packet["summary"]["controlled_research_inner_loops"] == 2
    assert packet["summary"]["build_requests_created"] == 1
    assert packet["summary"]["build_requests_pending"] == 1
    assert packet["summary"]["trading_status"] == "disabled"
    assert packet["summary"]["qre_operator_authority"] == "loop_only"
    assert packet["safety"]["paper_shadow_live_allowed"] is False
    assert packet["safety"]["broker_risk_allowed"] is False
    assert packet["safety"]["execution_allowed"] is False

    daily = (tmp_path / "daily" / "daily_status.md").read_text(encoding="utf-8")
    assert "# QRE Daily Status" in daily
    assert "QRE operator trust:" in daily
    assert "Research intelligence progress:" in daily
    assert "ADE/build progress:" in daily
    assert "Flywheel progress:" in daily
    assert "Artifact sources used:" in daily
    assert "Latest recommendation: add_cache_only_metric_path" in daily
    assert "The system does not rotate assets" in daily
    assert (tmp_path / "daily" / "scheduler_setup.md").exists()


def test_daily_digest_recognizes_merged_build_result(tmp_path: Path) -> None:
    loop_latest_path = _write_loop_latest(tmp_path)
    request_id = "build-request-1"
    _write_json(
        tmp_path / "loop" / "build_requests" / f"{request_id}.json",
        {"request_id": request_id, "next_action": "add_cache_only_metric_path", "safe_for_ade_build": True},
    )
    results_dir = tmp_path / "loop" / "build_results"
    results_dir.mkdir()
    (results_dir / f"{request_id}.json").write_text(
        json.dumps(
            {
                "request_id": request_id,
                "pr_number": 524,
                "merge_commit": "abc123",
                "status": "merged",
                "created_at_utc": "2026-06-13T00:00:00Z",
                "updated_main_commit": "abc123",
                "post_merge_research_required": True,
                "blocker_to_check": "safe_metric_runner_missing_or_cache_unavailable",
            }
        ),
        encoding="utf-8",
    )

    packet = digest.build_daily_status_packet(
        loop_latest_path=loop_latest_path,
        build_request_latest_path=tmp_path / "loop" / "latest_build_request.json",
        build_consumer_latest_path=tmp_path / "consumer" / "latest.json",
        backend_results_dir=tmp_path / "consumer" / "backend_results",
        pr_auto_merge_latest_path=tmp_path / "pr_gate" / "latest.json",
        runtime_continuation_latest_path=tmp_path / "runtime" / "latest.json",
        flywheel_latest_path=tmp_path / "flywheel" / "latest.json",
        trusted_loop_review_latest_path=tmp_path / "trusted_loop" / "latest.json",
        research_memory_current_artifacts_latest_path=tmp_path / "memory" / "latest.json",
        shadow_readiness_latest_path=tmp_path / "shadow" / "latest.json",
    )

    assert packet["summary"]["build_requests_pending"] == 0
    assert packet["summary"]["build_requests_completed_or_merged"] == 1
    assert packet["next_system_action"] == "add_cache_only_metric_path"


def test_digest_reads_build_consumer_latest_and_counts_consumed_build_request(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "latest.json",
        {
            "build_request_consumed": True,
            "pr_created": False,
            "blocked_reason": None,
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["build_requests_consumed"] == 1
    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["flywheel_progress"]["build_request_consumed"] == "yes"


def test_digest_reads_backend_result_and_counts_pr_opened(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "backend_results" / "build-request-1.json",
        {
            "created_at_utc": "2026-06-14T15:34:41Z",
            "build_request_consumed": True,
            "pr_created": True,
            "pr_number": 527,
            "pr_url": "https://github.com/roudjy/trading-agent/pull/527",
            "safe_for_auto_merge": True,
            "blocked_reason": None,
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["build_requests_consumed"] == 1
    assert packet["summary"]["prs_opened"] == 1
    assert packet["summary"]["flywheel_progress"]["pr_opened"] == "#527"


def test_digest_reads_pr_gate_latest_and_counts_pr_green_and_merged(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "pr_gate" / "latest.json",
        {
            "pr_number": 527,
            "pr_green": True,
            "pr_auto_merged": True,
            "auto_merge_allowed": True,
            "blocked_reasons": [],
            "manual_governance_required": False,
            "live_pr_status_queried": True,
            "ci_source": "live_gh_pr_view",
            "live_check_summary": {"success": 2, "failed": 0, "pending": 0},
            "merge_result": {"returncode": 0, "stdout": "merged", "stderr": ""},
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["prs_green"] == 1
    assert packet["summary"]["prs_merged"] == 1
    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["flywheel_progress"]["pr_green"] == "yes"
    assert packet["summary"]["flywheel_progress"]["pr_merged"] == "yes"


def test_digest_reads_runtime_latest_and_counts_update_and_continuation(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "runtime" / "latest.json",
        {
            "runtime_updated": True,
            "research_continuation_started": True,
            "research_cycles_started": 3,
            "blocked_reasons": [],
            "final_recommendation": "research_continuation_started",
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["runtime_updates_completed"] == 1
    assert packet["summary"]["research_continuations_started"] == 1
    assert packet["summary"]["latest_recommendation"] == "research_continuation_started"
    assert packet["summary"]["flywheel_progress"]["runtime_updated"] == "yes"
    assert packet["summary"]["flywheel_progress"]["research_continuation_started"] == "yes"


def test_digest_surfaces_qre_trust_memory_and_shadow_state(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "trusted_loop" / "latest.json",
        {
            "summary": {
                "trusted_loop_review_ready": False,
                "trust_verdict": "read_only_context_fail_closed",
                "trust_blocker_count": 3,
                "exact_next_action": "restore_trusted_loop_readiness_evidence",
            }
        },
    )
    _write_json(
        tmp_path / "memory" / "latest.json",
        {
            "summary": {
                "final_recommendation": "research_memory_current_artifacts_ready",
                "visible_source_authority_blocked_scope_count": 2,
                "source_authority_exact_next_action": "resolve_provider_symbol_ambiguity_for_bounded_scope",
            }
        },
    )
    _write_json(
        tmp_path / "shadow" / "latest.json",
        {
            "summary": {
                "readiness_status": "shadow_readiness_deferred",
                "blocker_count": 5,
                "exact_next_action": "produce_accepted_oos_and_evidence_complete_scope",
            }
        },
    )

    packet = _run_digest(
        tmp_path,
        trusted_loop_review_latest_path=tmp_path / "trusted_loop" / "latest.json",
        research_memory_current_artifacts_latest_path=tmp_path / "memory" / "latest.json",
        shadow_readiness_latest_path=tmp_path / "shadow" / "latest.json",
    )

    assert packet["summary"]["trusted_loop_review_ready"] is False
    assert packet["summary"]["trusted_loop_trust_verdict"] == "read_only_context_fail_closed"
    assert packet["summary"]["research_memory_current_artifacts_ready"] is True
    assert packet["summary"]["source_authority_blocked_scope_count"] == 2
    assert packet["summary"]["shadow_readiness_status"] == "shadow_readiness_deferred"
    assert packet["summary"]["qre_operator_authority"] == "working_read_only_fail_closed"
    assert packet["summary"]["qre_exact_next_action"] == "produce_accepted_oos_and_evidence_complete_scope"
    assert (
        packet["next_system_action"] == "produce_accepted_oos_and_evidence_complete_scope"
    )
    rendered = digest.render_daily_status(packet)
    assert "Source-authority blocked scope count: 2" in rendered
    assert "Source-authority exact next action: resolve_provider_symbol_ambiguity_for_bounded_scope" in rendered


def test_stale_no_safe_build_backend_configured_is_suppressed_after_successful_backend_result(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "latest.json",
        {
            "build_backend_available": False,
            "build_request_consumed": False,
            "pr_created": False,
            "blocked_reason": "no_safe_build_backend_configured",
            "missing_capability": "safe_build_backend",
            "protected_outputs_mutated": False,
        },
    )
    _write_json(
        tmp_path / "consumer" / "backend_results" / "build-request-1.json",
        {
            "created_at_utc": "2026-06-14T15:34:41Z",
            "build_backend_available": True,
            "build_request_consumed": True,
            "pr_created": True,
            "pr_number": 527,
            "blocked_reason": None,
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["prs_opened"] == 1


def test_active_blockers_are_still_shown_when_latest_artifact_has_real_blocked_reason(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "consumer" / "latest.json",
        {
            "build_request_consumed": False,
            "pr_created": False,
            "blocked_reason": "build_backend_failed",
            "missing_capability": None,
            "protected_outputs_mutated": False,
        },
    )

    packet = _run_digest(tmp_path)

    assert packet["summary"]["manual_governance_blockers"] == ["build_backend_failed"]
    assert packet["summary"]["latest_blocker"] == "build_backend_failed"


def test_protected_artifact_mutation_remains_surfaced_if_present(tmp_path: Path) -> None:
    loop_latest_path = _write_loop_latest(tmp_path, protected_outputs_mutated=True)

    packet = _run_digest(tmp_path, loop_latest_path=loop_latest_path)

    assert packet["summary"]["protected_artifact_mutation"] == "detected"


def test_trading_status_remains_disabled(tmp_path: Path) -> None:
    packet = _run_digest(tmp_path)

    assert packet["summary"]["trading_status"] == "disabled"
    assert packet["safety"]["paper_shadow_live_allowed"] is False
    assert packet["safety"]["broker_risk_allowed"] is False
    assert packet["safety"]["execution_allowed"] is False


def test_missing_artifacts_fail_gracefully_with_unknown_pending_status(tmp_path: Path) -> None:
    packet = _run_digest(tmp_path)

    assert packet["summary"]["build_requests_consumed"] == 0
    assert packet["summary"]["prs_opened"] == 0
    assert packet["summary"]["prs_green"] == 0
    assert packet["summary"]["prs_merged"] == 0
    assert packet["summary"]["runtime_updates_completed"] == 0
    assert packet["summary"]["research_continuations_started"] == 0
    assert packet["summary"]["manual_governance_blockers"] == []
    assert packet["summary"]["flywheel_progress"]["build_request_consumed"] == "unknown"
    assert packet["summary"]["flywheel_progress"]["pr_opened"] == "unknown"


def test_daily_digest_runs_when_tiingo_lifecycle_artifact_is_missing(tmp_path: Path) -> None:
    packet = _run_digest(tmp_path)

    lifecycle = packet["tiingo_hypothesis_lifecycle"]
    assert lifecycle["status"] == "not_available"
    assert packet["summary"]["tiingo_hypothesis_lifecycle_status"] == "not_available"
    assert packet["summary"]["trading_status"] == "disabled"
    assert packet["summary"]["manual_governance_blockers"] == []
    assert lifecycle["authority_summary"]["creates_candidates"] is False
    assert lifecycle["authority_summary"]["runs_screening"] is False
    assert lifecycle["authority_summary"]["trading_authority"] is False


def test_valid_tiingo_lifecycle_appears_in_structured_digest_output(tmp_path: Path) -> None:
    tiingo_path = _write_tiingo_lifecycle(tmp_path)

    packet = _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)

    lifecycle = packet["tiingo_hypothesis_lifecycle"]
    assert lifecycle == {
        "status": "ready",
        "source_artifact": tiingo_path.as_posix(),
        "report_kind": "qre_tiingo_hypothesis_lifecycle",
        "lifecycle_verdict": "pass_research_only_admission_boundary",
        "daily_digest_ready": True,
        "counts": {
            "generated": 5,
            "admitted": 5,
            "rejected": 0,
            "blocked": 0,
        },
        "hypotheses_seen": 5,
        "operator_updates_count": 10,
        "next_safe_actions": ["materialize_research_candidate_later"],
        "authority_summary": {
            "trading_authority": False,
            "creates_candidates": False,
            "runs_screening": False,
            "promotes_candidates": False,
            "registers_strategy": False,
            "validation_authority": False,
            "paper_authority": False,
            "shadow_authority": False,
            "live_authority": False,
        },
    }
    assert tiingo_path.as_posix() in packet["artifact_paths_used"]
    expected_counts = {
        "generated": 5,
        "admitted": 5,
        "rejected": 0,
        "blocked": 0,
    }
    expected_next_actions = ["materialize_research_candidate_later"]
    expected_authority = {
        "trading_authority": False,
        "creates_candidates": False,
        "runs_screening": False,
        "promotes_candidates": False,
        "registers_strategy": False,
        "validation_authority": False,
        "paper_authority": False,
        "shadow_authority": False,
        "live_authority": False,
    }
    assert packet["tiingo_hypothesis_lifecycle_status"] == "ready"
    assert packet["tiingo_hypothesis_lifecycle_counts"] == expected_counts
    assert packet["tiingo_hypothesis_lifecycle_next_actions"] == expected_next_actions
    assert packet["tiingo_hypothesis_lifecycle_authority"] == expected_authority
    assert packet["summary"]["tiingo_hypothesis_lifecycle_status"] == "ready"
    assert packet["summary"]["tiingo_hypothesis_lifecycle_counts"] == expected_counts
    assert packet["summary"]["tiingo_hypothesis_lifecycle_next_actions"] == expected_next_actions
    assert packet["summary"]["tiingo_hypothesis_lifecycle_authority"] == expected_authority


def test_valid_tiingo_lifecycle_writes_details_to_latest_json(tmp_path: Path) -> None:
    tiingo_path = _write_tiingo_lifecycle(tmp_path)

    _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)

    latest = json.loads((tmp_path / "daily" / "latest.json").read_text(encoding="utf-8"))
    assert latest["tiingo_hypothesis_lifecycle_status"] == "ready"
    assert latest["tiingo_hypothesis_lifecycle_counts"] == {
        "generated": 5,
        "admitted": 5,
        "rejected": 0,
        "blocked": 0,
    }
    assert latest["tiingo_hypothesis_lifecycle_next_actions"] == [
        "materialize_research_candidate_later"
    ]
    assert latest["tiingo_hypothesis_lifecycle_authority"]["creates_candidates"] is False
    assert latest["tiingo_hypothesis_lifecycle_authority"]["runs_screening"] is False
    assert latest["tiingo_hypothesis_lifecycle_authority"]["trading_authority"] is False


def test_valid_tiingo_lifecycle_appears_in_operator_summary(tmp_path: Path) -> None:
    tiingo_path = _write_tiingo_lifecycle(tmp_path)

    packet = _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)
    rendered = digest.render_daily_status(packet)

    assert "Tiingo hypothesis lifecycle:" in rendered
    assert "- Hypotheses generated: 5" in rendered
    assert "- Admitted: 5" in rendered
    assert "- Rejected: 0" in rendered
    assert "- Blocked: 0" in rendered
    assert "- Next safe action: materialize_research_candidate_later" in rendered
    assert "- Candidate creation: false" in rendered
    assert "- Screening run: false" in rendered
    assert "- Trading authority: false" in rendered
    assert "- Validation authority: false" in rendered
    assert "- Paper authority: false" in rendered
    assert "- Shadow authority: false" in rendered
    assert "- Live authority: false" in rendered
    assert "admitted for future research-only candidate formulation; candidate created: false" in rendered

    daily = (tmp_path / "daily" / "daily_status.md").read_text(encoding="utf-8")
    operator_summary = (tmp_path / "daily" / "operator_summary.md").read_text(encoding="utf-8")
    assert "- Hypotheses generated: 5" in daily
    assert "- Candidate creation: false" in daily
    assert "Tiingo hypothesis lifecycle:" in operator_summary
    assert "- Hypotheses generated: 5" in operator_summary
    assert "- Admitted: 5" in operator_summary
    assert "- Rejected: 0" in operator_summary
    assert "- Blocked: 0" in operator_summary
    assert "- Next safe action: materialize_research_candidate_later" in operator_summary
    assert "- Candidate creation: false" in operator_summary
    assert "- Screening run: false" in operator_summary
    assert "- Trading authority: false" in operator_summary


def test_unsafe_tiingo_lifecycle_authority_signal_is_blocked(tmp_path: Path) -> None:
    for unsafe_key in (
        "trading_authority",
        "creates_candidates",
        "runs_screening",
        "validation_authority",
        "paper_authority",
        "shadow_authority",
        "live_authority",
    ):
        payload = _valid_tiingo_lifecycle_payload()
        payload["safety"][unsafe_key] = True
        tiingo_path = _write_tiingo_lifecycle(tmp_path / unsafe_key, payload)

        packet = _run_digest(
            tmp_path / unsafe_key,
            tiingo_hypothesis_lifecycle_latest_path=tiingo_path,
        )

        lifecycle = packet["tiingo_hypothesis_lifecycle"]
        assert lifecycle["status"] == "blocked_unsafe_authority"
        assert lifecycle["diagnostic_reason"] == "unsafe_tiingo_lifecycle_authority_signal"
        assert unsafe_key in lifecycle["unsafe_authority_keys"]
        assert lifecycle["authority_summary"]["trading_authority"] is False
        assert lifecycle["authority_summary"]["creates_candidates"] is False
        assert lifecycle["authority_summary"]["runs_screening"] is False
        assert packet["tiingo_hypothesis_lifecycle_authority"]["trading_authority"] is False
        assert packet["tiingo_hypothesis_lifecycle_authority"]["creates_candidates"] is False
        assert packet["tiingo_hypothesis_lifecycle_authority"]["runs_screening"] is False


def test_malformed_tiingo_lifecycle_artifact_is_reported_without_crashing(tmp_path: Path) -> None:
    tiingo_path = tmp_path / "tiingo_lifecycle" / "latest.json"
    tiingo_path.parent.mkdir(parents=True, exist_ok=True)
    tiingo_path.write_text("{not-json", encoding="utf-8")

    packet = _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)

    lifecycle = packet["tiingo_hypothesis_lifecycle"]
    assert lifecycle["status"] == "malformed_or_unreadable"
    assert lifecycle["diagnostic_reason"] == "tiingo_hypothesis_lifecycle_artifact_unreadable"
    assert lifecycle["authority_summary"]["trading_authority"] is False


def test_tiingo_lifecycle_daily_digest_ready_false_is_not_actionable(tmp_path: Path) -> None:
    payload = _valid_tiingo_lifecycle_payload()
    payload["summary"]["daily_digest_ready"] = False
    tiingo_path = _write_tiingo_lifecycle(tmp_path, payload)

    packet = _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)

    lifecycle = packet["tiingo_hypothesis_lifecycle"]
    assert lifecycle["status"] == "not_ready"
    assert lifecycle["counts"] == {
        "generated": 0,
        "admitted": 0,
        "rejected": 0,
        "blocked": 0,
    }
    assert lifecycle["observed_counts"] == {
        "generated": 5,
        "admitted": 5,
        "rejected": 0,
        "blocked": 0,
    }
    assert lifecycle["next_safe_actions"] == []


def test_tiingo_lifecycle_ingestion_does_not_mutate_protected_research_outputs(tmp_path: Path) -> None:
    research_latest = Path("research/research_latest.json")
    strategy_matrix = Path("research/strategy_matrix.csv")
    before_latest = research_latest.read_bytes()
    before_matrix = strategy_matrix.read_bytes()
    tiingo_path = _write_tiingo_lifecycle(tmp_path)

    packet = _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)

    assert research_latest.read_bytes() == before_latest
    assert strategy_matrix.read_bytes() == before_matrix
    assert packet["tiingo_hypothesis_lifecycle"]["authority_summary"]["creates_candidates"] is False
    assert packet["tiingo_hypothesis_lifecycle"]["authority_summary"]["runs_screening"] is False


def test_tiingo_lifecycle_ingestion_does_not_create_candidates_or_run_screening(tmp_path: Path) -> None:
    tiingo_path = _write_tiingo_lifecycle(tmp_path)

    packet = _run_digest(tmp_path, tiingo_hypothesis_lifecycle_latest_path=tiingo_path)

    authority = packet["tiingo_hypothesis_lifecycle_authority"]
    assert authority["creates_candidates"] is False
    assert authority["runs_screening"] is False
    assert authority["trading_authority"] is False
    assert authority["validation_authority"] is False
    assert authority["paper_authority"] is False
    assert authority["shadow_authority"] is False
    assert authority["live_authority"] is False


def test_missing_tiingo_candidate_loop_artifact_is_not_available(tmp_path: Path) -> None:
    packet = _run_digest(tmp_path)

    assert packet["tiingo_candidate_loop_status"] == "not_available"
    assert packet["tiingo_candidate_loop_counts"]["candidates_materialized"] == 0
    assert packet["tiingo_candidate_loop_authority"]["trading_authority"] is False


def test_valid_tiingo_candidate_loop_appears_in_digest_json(tmp_path: Path) -> None:
    candidate_path = _write_tiingo_candidate_loop(tmp_path)

    packet = _run_digest(tmp_path, tiingo_candidate_loop_latest_path=candidate_path)

    assert packet["tiingo_candidate_loop_status"] == "ready"
    assert packet["tiingo_candidate_loop_counts"] == {
        "contracts": 5,
        "candidates_materialized": 5,
        "candidates_screened": 5,
        "screening_pass": 2,
        "screening_fail": 0,
        "null_not_beaten": 3,
        "insufficient_evidence": 0,
        "feedback_records": 5,
        "evidence_records": 5,
    }
    assert packet["tiingo_candidate_loop_feedback"] == {
        "feedback_consumed": False,
        "feedback_applied_count": 0,
        "next_run_feedback_ready": True,
    }
    assert packet["tiingo_candidate_loop_variants"] == {
        "base_candidates": 5,
        "variant_candidates": 0,
        "variants_materialized": 0,
        "modified_by_prior_feedback": 0,
        "retained_by_prior_feedback": 0,
        "suppressed_by_prior_feedback": 0,
    }
    assert packet["tiingo_candidate_loop_authority"]["research_only"] is True
    assert packet["tiingo_candidate_loop_authority"]["screening_only"] is True
    assert packet["tiingo_candidate_loop_authority"]["trading_authority"] is False
    assert packet["summary"]["tiingo_candidate_loop_counts"]["evidence_records"] == 5
    assert packet["summary"]["tiingo_candidate_loop_feedback"]["feedback_consumed"] is False


def test_tiingo_candidate_loop_operator_summary_section(tmp_path: Path) -> None:
    candidate_path = _write_tiingo_candidate_loop(tmp_path)

    _run_digest(tmp_path, tiingo_candidate_loop_latest_path=candidate_path)

    rendered = (tmp_path / "daily" / "operator_summary.md").read_text(encoding="utf-8")
    assert "Tiingo candidate research loop:" in rendered
    assert "- Contracts admitted: 5" in rendered
    assert "- Candidates materialized: 5" in rendered
    assert "- Candidates screened: 5" in rendered
    assert "- Evidence records: 5" in rendered
    assert "- Feedback consumed: false" in rendered
    assert "- Feedback applied count: 0" in rendered
    assert "- Base candidates: 5" in rendered
    assert "- Variant candidates: 0" in rendered
    assert "- Candidate creation: research-only specs" in rendered
    assert "Candidate creation means research-only candidate specs, not executable strategies." in rendered
    assert "- Trading authority: false" in rendered
    assert "- Validation authority: false" in rendered
    assert "- Paper authority: false" in rendered
    assert "- Shadow authority: false" in rendered
    assert "- Live authority: false" in rendered


def test_unsafe_tiingo_candidate_loop_authority_is_blocked(tmp_path: Path) -> None:
    payload = _valid_tiingo_candidate_loop_payload()
    payload["safety"]["trading_authority"] = True
    candidate_path = _write_tiingo_candidate_loop(tmp_path, payload)

    packet = _run_digest(tmp_path, tiingo_candidate_loop_latest_path=candidate_path)

    assert packet["tiingo_candidate_loop_status"] == "blocked_unsafe_authority"
    assert packet["tiingo_candidate_loop_authority"]["trading_authority"] is False
    assert packet["tiingo_candidate_loop_authority"]["research_only"] is True


def test_malformed_tiingo_candidate_loop_artifact_is_reported(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate_loop" / "latest.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text("{not-json", encoding="utf-8")

    packet = _run_digest(tmp_path, tiingo_candidate_loop_latest_path=candidate_path)

    assert packet["tiingo_candidate_loop_status"] == "malformed_or_unreadable"
    assert packet["tiingo_candidate_loop_authority"]["trading_authority"] is False


def test_daily_digest_candidate_loop_ingestion_does_not_create_candidates_or_screening(tmp_path: Path) -> None:
    candidate_path = _write_tiingo_candidate_loop(tmp_path)

    packet = _run_digest(tmp_path, tiingo_candidate_loop_latest_path=candidate_path)

    assert packet["tiingo_candidate_loop_counts"]["candidates_materialized"] == 5
    assert packet["tiingo_candidate_loop_counts"]["candidates_screened"] == 5
    assert packet["safety"]["run_research_called"] is False
    assert packet["safety"]["validation_executed"] is False
    assert packet["safety"]["execution_allowed"] is False
    assert packet["tiingo_candidate_loop_authority"]["creates_orders"] is False
    assert packet["tiingo_candidate_loop_authority"]["promotes_candidates"] is False

