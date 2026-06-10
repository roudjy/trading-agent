from pathlib import Path

import pytest

from research.qre_trusted_loop_review_packet import (
    build_trusted_loop_review_packet,
    render_operator_summary,
    write_outputs,
)


def test_trusted_loop_review_packet_is_ready_and_context_only():
    packet = build_trusted_loop_review_packet()

    assert packet["schema_version"] == "1.0"
    assert packet["report_kind"] == "qre_trusted_loop_review_packet"
    assert packet["summary"]["trusted_loop_review_ready"] is True
    assert packet["summary"]["final_recommendation"] == "trusted_loop_ready_for_operator_review_not_execution"

    boundaries = packet["authority_boundaries"]
    assert boundaries["review_packet_is_context_only"] is True
    assert boundaries["not_alpha_authority"] is True
    assert boundaries["not_queue_mutation"] is True
    assert boundaries["not_candidate_promotion"] is True
    assert boundaries["not_campaign_mutation"] is True
    assert boundaries["not_strategy_registration"] is True
    assert boundaries["not_preset_mutation"] is True
    assert boundaries["not_trade_signal_generation"] is True
    assert boundaries["not_provider_activation"] is True
    assert boundaries["not_data_fetching"] is True
    assert boundaries["not_paper_shadow_live"] is True
    assert boundaries["not_broker_execution"] is True
    assert boundaries["not_risk_authority"] is True
    assert boundaries["does_not_mutate_frozen_contracts"] is True
    assert boundaries["does_not_mutate_research_latest"] is True
    assert boundaries["does_not_mutate_strategy_matrix"] is True


def test_trusted_loop_review_packet_lists_all_capability_stages():
    packet = build_trusted_loop_review_packet()

    capability_ids = {row["capability_id"] for row in packet["capabilities"]}
    assert capability_ids == {"A", "B", "C", "D", "E", "F"}
    assert packet["summary"]["capability_count"] == 6
    assert packet["summary"]["implemented_capability_count"] == 6


def test_trusted_loop_review_packet_lists_expected_report_surfaces():
    packet = build_trusted_loop_review_packet()

    report_kinds = {row["report_kind"] for row in packet["report_surfaces"]}

    assert "qre_null_model_baseline_report" in report_kinds
    assert "qre_state_transition_diagnostics_report" in report_kinds
    assert "qre_tail_entropy_hardening_report" in report_kinds
    assert "qre_sampling_calibration_report" in report_kinds
    assert "qre_routing_calibration_report" in report_kinds
    assert "qre_trusted_loop_review_packet" in report_kinds


def test_trusted_loop_review_packet_scope_policy_excludes_crypto_and_prefers_equity():
    packet = build_trusted_loop_review_packet()
    policy = packet["current_scope_policy"]

    assert policy["crypto_legacy"] == "excluded_from_current_research_scope_and_archive_only"
    assert "fundamental_equity" in policy["preferred_sampling_axes"]
    assert "netherlands" in policy["preferred_sampling_axes"]
    assert "united_states" in policy["preferred_sampling_axes"]
    assert "asia" in policy["preferred_sampling_axes"]
    assert "excluded_scope_archive" in policy["routing_context_targets"]


def test_trusted_loop_review_packet_tracks_protected_artifacts():
    packet = build_trusted_loop_review_packet()

    paths = {row["path"] for row in packet["protected_artifacts"]}
    assert "research/research_latest.json" in paths
    assert "research/strategy_matrix.csv" in paths


def test_trusted_loop_review_packet_operator_summary_renders():
    packet = build_trusted_loop_review_packet()
    text = render_operator_summary(packet)

    assert "# QRE Trusted Loop Review Packet" in text
    assert "trusted_loop_ready_for_operator_review_not_execution" in text
    assert "Authority Boundary" in text


def test_trusted_loop_review_packet_write_outputs_stays_in_allowlist(tmp_path: Path):
    packet = build_trusted_loop_review_packet(repo_root=tmp_path)
    paths = write_outputs(packet, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_trusted_loop_review/latest.json"
    assert paths["operator_summary"] == "logs/qre_trusted_loop_review/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_trusted_loop_review_packet_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_trusted_loop_review_packet as packet_module

    monkeypatch.setattr(packet_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    packet = build_trusted_loop_review_packet(repo_root=tmp_path)

    with pytest.raises(ValueError):
        write_outputs(packet, repo_root=tmp_path)