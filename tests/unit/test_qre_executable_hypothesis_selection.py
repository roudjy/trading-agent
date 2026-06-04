from __future__ import annotations

from dataclasses import replace

import reporting.qre_executable_hypothesis_selection as selection
from research.presets import PRESETS


def test_default_crypto_profile_selects_three_catalog_entries() -> None:
    snapshot = selection.collect_snapshot(generated_at_utc="2026-06-03T12:00:00Z")

    assert snapshot["report_kind"] == "qre_executable_hypothesis_selection"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False
    assert snapshot["counts"]["total"] == 3
    assert snapshot["counts"]["selected"] == 3
    assert snapshot["counts"]["blocked"] == 0
    assert (
        snapshot["final_recommendation"]
        == "executable_hypothesis_selections_ready_for_operator_review"
    )

    rows = snapshot["selection_rows"]
    assert {row["preset_name"] for row in rows} == {
        "trend_pullback_crypto_1h",
        "vol_compression_breakout_crypto_1h",
        "vol_compression_breakout_crypto_4h",
    }


def test_strategy_template_id_is_resolved_from_preset_bundle() -> None:
    snapshot = selection.collect_snapshot(generated_at_utc="2026-06-03T12:00:00Z")
    rows_by_preset = {row["preset_name"]: row for row in snapshot["selection_rows"]}

    assert rows_by_preset["trend_pullback_crypto_1h"]["strategy_template_id"] == "trend_pullback_v1"
    assert (
        rows_by_preset["vol_compression_breakout_crypto_1h"]["strategy_template_id"]
        == "volatility_compression_breakout"
    )
    assert (
        rows_by_preset["vol_compression_breakout_crypto_4h"]["strategy_template_id"]
        == "volatility_compression_breakout"
    )


def test_selection_rows_remain_non_executing_operator_review_only() -> None:
    snapshot = selection.collect_snapshot(generated_at_utc="2026-06-03T12:00:00Z")

    for row in snapshot["selection_rows"]:
        assert row["selection_status"] == "selected"
        assert row["safe_to_execute"] is False
        assert row["eligible_for_direct_execution"] is False
        assert row["requires_operator_approval"] is True
        assert row["selection_source"] == "research.discovery_sprint.derive_plan"
        assert "operator_review_required" in row["reason_codes"]


def test_unknown_profile_fails_closed() -> None:
    snapshot = selection.collect_snapshot(
        profile_name="does_not_exist",
        generated_at_utc="2026-06-03T12:00:00Z",
    )

    assert snapshot["counts"]["total"] == 0
    assert snapshot["counts"]["selected"] == 0
    assert snapshot["counts"]["blocked"] == 0
    assert snapshot["selection_rows"] == []
    assert snapshot["validation_warnings"] == ["selection_profile_not_found"]
    assert snapshot["final_recommendation"] == "executable_hypothesis_selection_blocked"
    assert snapshot["safe_to_execute"] is False


def test_missing_preset_bundle_fails_closed() -> None:
    mutated_presets = []
    for preset in PRESETS:
        if preset.name == "trend_pullback_crypto_1h":
            mutated_presets.append(replace(preset, bundle=()))
        else:
            mutated_presets.append(preset)

    snapshot = selection.collect_snapshot(
        generated_at_utc="2026-06-03T12:00:00Z",
        presets=tuple(mutated_presets),
    )

    rows_by_preset = {row["preset_name"]: row for row in snapshot["selection_rows"]}
    trend_row = rows_by_preset["trend_pullback_crypto_1h"]

    assert trend_row["selection_status"] == "selection_preset_bundle_empty"
    assert trend_row["strategy_template_id"] is None
    assert trend_row["safe_to_execute"] is False
    assert snapshot["counts"]["total"] == 3
    assert snapshot["counts"]["selected"] == 2
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["final_recommendation"] == "executable_hypothesis_selection_blocked"


def test_no_write_cli_does_not_write_artifact(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(selection, "ARTIFACT_LATEST", artifact_path)

    rc = selection.main(
        [
            "--no-write",
            "--frozen-utc",
            "2026-06-03T12:00:00Z",
            "--indent",
            "2",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()


def test_cli_writes_only_requested_artifact_path(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(selection, "ARTIFACT_LATEST", artifact_path)

    rc = selection.main(
        [
            "--frozen-utc",
            "2026-06-03T12:00:00Z",
            "--indent",
            "2",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    text = artifact_path.read_text(encoding="utf-8")
    assert '"report_kind": "qre_executable_hypothesis_selection"' in text
    assert '"safe_to_execute": false' in text


def test_selection_rows_can_feed_request_and_dry_run_route(tmp_path) -> None:
    import json

    import reporting.qre_executable_validation_request as request
    import reporting.qre_market_observation_hypothesis_readiness as readiness
    import reporting.qre_validation_request_dry_run_runner as dry_run

    frozen = "2026-06-03T13:30:00Z"
    snapshot = selection.collect_snapshot(generated_at_utc=frozen)
    rows = snapshot["selection_rows"]

    observations = []
    hypotheses = []
    validation_plans = []
    run_manifests = []

    for index, row in enumerate(rows, start=1):
        qre_hypothesis_id = f"qre-hyp-selection-test-{index:03d}"
        validation_plan_id = f"qre-plan-selection-test-{index:03d}"
        run_manifest_id = f"qre-run-selection-test-{index:03d}"
        observation_id = f"qre-obs-selection-test-{index:03d}"

        observations.append(
            {
                "observation_id": observation_id,
                "observation_type": "executable_hypothesis_selection",
                "source_artifact": "logs/qre_executable_hypothesis_selection/latest.json",
                "source_report_kind": "qre_executable_hypothesis_selection",
                "source_row_id": row["selection_id"],
                "supporting_evidence_refs": row["supporting_evidence_refs"],
                "asset": row["asset"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "interval": row["interval"],
                "preset_name": row["preset_name"],
                "strategy_family": row["strategy_family"],
                "strategy_template_id": row["strategy_template_id"],
                "executable_hypothesis_id": row["executable_hypothesis_id"],
                "source_hypothesis_id": row["source_hypothesis_id"],
                "summary": row["summary"],
            }
        )
        hypotheses.append(
            {
                "hypothesis_id": qre_hypothesis_id,
                "source_observation_id": observation_id,
                "source_artifact": "logs/qre_executable_hypothesis_selection/latest.json",
                "source_report_kind": "qre_executable_hypothesis_selection",
                "source_row_id": row["selection_id"],
                "supporting_evidence_refs": row["supporting_evidence_refs"],
                "asset": row["asset"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "interval": row["interval"],
                "preset_name": row["preset_name"],
                "strategy_family": row["strategy_family"],
                "strategy_template_id": row["strategy_template_id"],
                "executable_hypothesis_id": row["executable_hypothesis_id"],
                "source_hypothesis_id": row["source_hypothesis_id"],
            }
        )
        validation_plans.append(
            {
                "validation_plan_id": validation_plan_id,
                "hypothesis_id": qre_hypothesis_id,
                "executable_hypothesis_id": row["executable_hypothesis_id"],
                "preset_name": row["preset_name"],
                "strategy_family": row["strategy_family"],
                "strategy_template_id": row["strategy_template_id"],
                "asset": row["asset"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "interval": row["interval"],
            }
        )
        run_manifests.append(
            {
                "run_manifest_id": run_manifest_id,
                "target_validation_plan_id": validation_plan_id,
                "hypothesis_id": qre_hypothesis_id,
                "executable_hypothesis_id": row["executable_hypothesis_id"],
                "preset_name": row["preset_name"],
                "asset": row["asset"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "interval": row["interval"],
            }
        )

    market_observation_path = tmp_path / "market_observations.json"
    hypothesis_path = tmp_path / "hypothesis_candidates.json"
    validation_plan_path = tmp_path / "validation_plans.json"
    run_manifest_path = tmp_path / "run_manifest.json"
    readiness_path = tmp_path / "readiness.json"
    request_path = tmp_path / "request.json"

    market_observation_path.write_text(
        json.dumps(
            {
                "report_kind": "qre_market_observation_snapshot",
                "schema_version": "test",
                "generated_at_utc": frozen,
                "observations": observations,
            }
        ),
        encoding="utf-8",
    )
    hypothesis_path.write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_candidates",
                "schema_version": "test",
                "generated_at_utc": frozen,
                "hypotheses": hypotheses,
            }
        ),
        encoding="utf-8",
    )
    validation_plan_path.write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_validation_plan",
                "schema_version": "test",
                "generated_at_utc": frozen,
                "validation_plans": validation_plans,
            }
        ),
        encoding="utf-8",
    )
    run_manifest_path.write_text(
        json.dumps(
            {
                "report_kind": "qre_research_run_manifest",
                "schema_version": "test",
                "generated_at_utc": frozen,
                "run_manifests": run_manifests,
            }
        ),
        encoding="utf-8",
    )

    readiness_snapshot = readiness.collect_snapshot(
        input_artifact_path=market_observation_path,
        generated_at_utc=frozen,
    )
    readiness_path.write_text(json.dumps(readiness_snapshot), encoding="utf-8")

    request_snapshot = request.collect_snapshot(
        input_artifact_path=hypothesis_path,
        readiness_artifact_path=readiness_path,
        market_observation_artifact_path=market_observation_path,
        validation_plan_artifact_path=validation_plan_path,
        run_manifest_artifact_path=run_manifest_path,
        generated_at_utc=frozen,
    )

    assert request_snapshot["counts"]["total"] == 3
    assert request_snapshot["counts"]["ready"] == 3
    assert request_snapshot["counts"]["blocked"] == 0
    assert request_snapshot["counts"]["by_request_status"]["request_ready_for_operator_review"] == 3

    request_path.write_text(json.dumps(request_snapshot), encoding="utf-8")

    dry_run_snapshot = dry_run.collect_snapshot(
        input_artifact_path=request_path,
        generated_at_utc=frozen,
    )

    assert dry_run_snapshot["counts"]["total"] == 3
    assert dry_run_snapshot["counts"]["ready"] == 3
    assert dry_run_snapshot["counts"]["blocked"] == 0
    assert dry_run_snapshot["counts"]["by_dry_run_status"]["dry_run_ready"] == 3
    assert dry_run_snapshot["executed_anything"] is False

    for row in dry_run_snapshot["dry_run_results"]:
        assert row["dry_run_status"] == "dry_run_ready"
        assert row["safe_to_execute"] is False
        assert row["executed"] is False
        assert row["would_run_command_preview"]

def test_equities_profile_selects_trend_pullback_equities_4h_only() -> None:
    snapshot = selection.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T12:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_executable_hypothesis_selection"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False
    assert snapshot["launches_codex"] is False
    assert snapshot["launches_subprocess"] is False
    assert snapshot["mutates_strategy_or_preset"] is False
    assert snapshot["mutates_campaign_queue"] is False
    assert snapshot["mutates_paper_shadow_live_runtime"] is False

    assert snapshot["selection_profile_name"] == "equities_exploratory_v1"
    assert snapshot["counts"]["selected"] == 1
    assert snapshot["counts"]["blocked"] == 0
    assert snapshot["counts"]["total"] == 1
    assert snapshot["final_recommendation"] == (
        "executable_hypothesis_selections_ready_for_operator_review"
    )

    rows = snapshot["selection_rows"]
    assert [row["preset_name"] for row in rows] == ["trend_pullback_equities_4h"]
    row = rows[0]
    assert row["source_hypothesis_id"] == "trend_pullback_v1"
    assert row["executable_hypothesis_id"] == "trend_pullback_v1"
    assert row["asset"] == "NVDA"
    assert row["symbol"] == "NVDA"
    assert row["timeframe"] == "4h"
    assert row["interval"] == "4h"
    assert row["asset_class"] == "equity"
    assert row["selection_status"] == "selected"
    assert row["requires_operator_approval"] is True
    assert row["safe_to_execute"] is False

