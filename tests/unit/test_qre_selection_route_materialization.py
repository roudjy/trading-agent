from __future__ import annotations

import json

import reporting.qre_selection_route_materialization as materialization


def test_materializes_selection_route_artifacts() -> None:
    snapshot = materialization.collect_snapshot(generated_at_utc="2026-06-03T14:00:00Z")

    assert snapshot["report_kind"] == "qre_selection_route_materialization"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False
    assert snapshot["counts"]["observations"] == 3
    assert snapshot["counts"]["hypotheses"] == 3
    assert snapshot["counts"]["validation_plans"] == 3
    assert snapshot["counts"]["run_manifests"] == 3
    assert snapshot["counts"]["materialized_route_ready"] == 3
    assert snapshot["final_recommendation"] == "selection_route_materialized_for_validation_request"


def test_payloads_have_qre_report_kinds_and_required_rows() -> None:
    snapshot = materialization.collect_snapshot(generated_at_utc="2026-06-03T14:00:00Z")

    assert (
        snapshot["market_observation_payload"]["report_kind"] == "qre_market_observation_snapshot"
    )
    assert snapshot["hypothesis_candidates_payload"]["report_kind"] == "qre_hypothesis_candidates"
    assert snapshot["validation_plans_payload"]["report_kind"] == "qre_hypothesis_validation_plan"
    assert snapshot["run_manifest_payload"]["report_kind"] == "qre_research_run_manifest"

    observations = snapshot["market_observation_payload"]["observations"]
    hypotheses = snapshot["hypothesis_candidates_payload"]["hypotheses"]
    plans = snapshot["validation_plans_payload"]["validation_plans"]
    manifests = snapshot["run_manifest_payload"]["run_manifests"]

    assert len(observations) == len(hypotheses) == len(plans) == len(manifests) == 3


def test_materialized_rows_preserve_executable_identity_and_linkage() -> None:
    snapshot = materialization.collect_snapshot(generated_at_utc="2026-06-03T14:00:00Z")

    observations = snapshot["market_observation_payload"]["observations"]
    hypotheses = snapshot["hypothesis_candidates_payload"]["hypotheses"]
    plans = snapshot["validation_plans_payload"]["validation_plans"]
    manifests = snapshot["run_manifest_payload"]["run_manifests"]

    observations_by_id = {row["observation_id"]: row for row in observations}
    plans_by_hypothesis = {row["hypothesis_id"]: row for row in plans}
    manifests_by_plan = {row["target_validation_plan_id"]: row for row in manifests}

    for hypothesis in hypotheses:
        observation = observations_by_id[hypothesis["source_observation_id"]]
        plan = plans_by_hypothesis[hypothesis["hypothesis_id"]]
        manifest = manifests_by_plan[plan["validation_plan_id"]]

        assert hypothesis["executable_hypothesis_id"]
        assert hypothesis["source_hypothesis_id"] == hypothesis["executable_hypothesis_id"]
        assert hypothesis["preset_name"]
        assert hypothesis["strategy_family"]
        assert hypothesis["strategy_template_id"]
        assert hypothesis["asset"]
        assert hypothesis["timeframe"]
        assert hypothesis["summary"]
        assert hypothesis["supporting_evidence_refs"]

        assert observation["executable_hypothesis_id"] == hypothesis["executable_hypothesis_id"]
        assert observation["preset_name"] == hypothesis["preset_name"]
        assert observation["strategy_template_id"] == hypothesis["strategy_template_id"]

        assert plan["hypothesis_id"] == hypothesis["hypothesis_id"]
        assert plan["executable_hypothesis_id"] == hypothesis["executable_hypothesis_id"]
        assert plan["preset_name"] == hypothesis["preset_name"]

        assert manifest["hypothesis_id"] == hypothesis["hypothesis_id"]
        assert manifest["run_manifest_id"]
        assert manifest["executable_hypothesis_id"] == hypothesis["executable_hypothesis_id"]


def test_materialized_observations_are_hypothesis_ready() -> None:
    import reporting.qre_market_observation_hypothesis_readiness as readiness

    snapshot = materialization.collect_snapshot(generated_at_utc="2026-06-03T14:00:00Z")
    observations = snapshot["market_observation_payload"]["observations"]

    classifications = [readiness.classify_observation(row) for row in observations]

    assert {row["readiness_class"] for row in classifications} == {"hypothesis_ready"}


def test_materialized_route_feeds_request_and_dry_run(tmp_path) -> None:
    import reporting.qre_executable_validation_request as request
    import reporting.qre_market_observation_hypothesis_readiness as readiness
    import reporting.qre_validation_request_dry_run_runner as dry_run

    frozen = "2026-06-03T14:00:00Z"
    snapshot = materialization.collect_snapshot(generated_at_utc=frozen)

    market_path = tmp_path / "market.json"
    hypotheses_path = tmp_path / "hypotheses.json"
    plans_path = tmp_path / "plans.json"
    manifests_path = tmp_path / "manifests.json"
    readiness_path = tmp_path / "readiness.json"
    request_path = tmp_path / "request.json"

    market_path.write_text(
        json.dumps(snapshot["market_observation_payload"]),
        encoding="utf-8",
    )
    hypotheses_path.write_text(
        json.dumps(snapshot["hypothesis_candidates_payload"]),
        encoding="utf-8",
    )
    plans_path.write_text(
        json.dumps(snapshot["validation_plans_payload"]),
        encoding="utf-8",
    )
    manifests_path.write_text(
        json.dumps(snapshot["run_manifest_payload"]),
        encoding="utf-8",
    )

    readiness_snapshot = readiness.collect_snapshot(
        input_artifact_path=market_path,
        generated_at_utc=frozen,
    )
    readiness_path.write_text(json.dumps(readiness_snapshot), encoding="utf-8")

    request_snapshot = request.collect_snapshot(
        input_artifact_path=hypotheses_path,
        readiness_artifact_path=readiness_path,
        market_observation_artifact_path=market_path,
        validation_plan_artifact_path=plans_path,
        run_manifest_artifact_path=manifests_path,
        generated_at_utc=frozen,
    )
    request_path.write_text(json.dumps(request_snapshot), encoding="utf-8")

    assert request_snapshot["counts"]["total"] == 3
    assert request_snapshot["counts"]["ready"] == 3
    assert request_snapshot["counts"]["blocked"] == 0
    assert request_snapshot["counts"]["by_request_status"]["request_ready_for_operator_review"] == 3

    dry_run_snapshot = dry_run.collect_snapshot(
        input_artifact_path=request_path,
        generated_at_utc=frozen,
    )

    assert dry_run_snapshot["counts"]["total"] == 3
    assert dry_run_snapshot["counts"]["ready"] == 3
    assert dry_run_snapshot["counts"]["blocked"] == 0
    assert dry_run_snapshot["counts"]["by_dry_run_status"]["dry_run_ready"] == 3
    assert dry_run_snapshot["executed_anything"] is False


def test_unselected_rows_fail_closed() -> None:
    selection_snapshot = {
        "report_kind": "qre_executable_hypothesis_selection",
        "counts": {"selected": 0, "blocked": 1, "total": 1},
        "selection_rows": [
            {
                "selection_id": "sel-blocked",
                "selection_status": "selection_preset_bundle_empty",
            }
        ],
    }

    snapshot = materialization.collect_snapshot(
        selection_snapshot=selection_snapshot,
        generated_at_utc="2026-06-03T14:00:00Z",
    )

    assert snapshot["counts"]["materialized_route_ready"] == 0
    assert snapshot["validation_warnings"] == ["selection_row_not_selected:sel-blocked"]
    assert snapshot["final_recommendation"] == "selection_route_materialization_blocked"


def test_no_write_cli_does_not_write_artifact(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(materialization, "ARTIFACT_LATEST", artifact_path)

    rc = materialization.main(
        [
            "--no-write",
            "--frozen-utc",
            "2026-06-03T14:00:00Z",
            "--indent",
            "2",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(materialization, "ARTIFACT_LATEST", artifact_path)

    rc = materialization.main(
        [
            "--frozen-utc",
            "2026-06-03T14:00:00Z",
            "--indent",
            "2",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "qre_selection_route_materialization"
    assert payload["safe_to_execute"] is False
    assert payload["counts"]["materialized_route_ready"] == 3

def test_materializes_equities_profile_route_artifacts() -> None:
    snapshot = materialization.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T14:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_selection_route_materialization"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["counts"]["observations"] == 1
    assert snapshot["counts"]["hypotheses"] == 1
    assert snapshot["counts"]["validation_plans"] == 1
    assert snapshot["counts"]["run_manifests"] == 1
    assert snapshot["counts"]["materialized_route_ready"] == 1
    assert snapshot["final_recommendation"] == "selection_route_materialized_for_validation_request"

    observations = snapshot["market_observation_payload"]["observations"]
    hypotheses = snapshot["hypothesis_candidates_payload"]["hypotheses"]
    plans = snapshot["validation_plans_payload"]["validation_plans"]
    manifests = snapshot["run_manifest_payload"]["run_manifests"]

    assert [row["asset"] for row in observations] == ["NVDA"]
    assert [row["timeframe"] for row in observations] == ["4h"]
    assert observations[0]["market_context"]["selection_profile_name"] == (
        "equities_exploratory_v1"
    )
    assert [row["preset_name"] for row in hypotheses] == ["trend_pullback_equities_4h"]
    assert [row["asset"] for row in plans] == ["NVDA"]
    assert [row["timeframe"] for row in manifests] == ["4h"]

