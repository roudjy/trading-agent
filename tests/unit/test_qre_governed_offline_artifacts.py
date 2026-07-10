from __future__ import annotations

from pathlib import Path

from packages.qre_research import evidence_memory_accumulation as accumulation
from packages.qre_research import governed_candidate_batch as batch
from packages.qre_research import governed_offline_artifacts as artifacts
from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import offline_research_dry_run as dry_run
from packages.qre_research import operator_trust_multirun_report as trust_report
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUTPUTS = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


def _proposal(hypothesis_id: str) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="synthetic trend persistence",
        source_id="source_fixture",
        behavior_family="trend",
        expected_information_gain=50.0,
    )


def _candidate(hypothesis_id: str, **kwargs: object) -> throughput.ThroughputCandidate:
    return throughput.ThroughputCandidate(
        proposal=_proposal(hypothesis_id),
        timeframe="1h",
        **kwargs,
    )


def _budget() -> throughput.ThroughputBudget:
    return throughput.ThroughputBudget(3, 3, 3, 3, 3)


def _envelope() -> dict[str, object]:
    missing = reasons.make_reason_record(
        code="evidence_incomplete",
        stage="EvidencePack",
        object_id="blocked",
        explanation="Evidence incomplete.",
        next_action="collect_missing_evidence",
    )
    negative = reasons.make_reason_record(
        code="data_quality_failed",
        stage="SourceSnapshot",
        object_id="blocked",
        explanation="Data quality failed.",
        next_action="repair_source_data_quality",
    )
    candidate = _candidate("blocked", data_quality_admitted=False)
    result = dry_run.run_offline_dry_run(candidate, budget=_budget(), rejection_records=(missing, negative))
    batch_result = batch.run_governed_candidate_batch(
        "batch-artifact",
        (candidate,),
        budget=_budget(),
        rejection_records=(missing, negative),
    )
    accumulated = accumulation.accumulate_evidence_memory((batch_result,))
    report = trust_report.build_operator_trust_multirun_report(accumulated)
    return artifacts.build_artifact_envelope(
        run_id="run-001",
        dry_run_result=result,
        operator_report=report,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_artifact_envelope_validates_and_contains_required_sections() -> None:
    envelope = _envelope()

    assert artifacts.validate_artifact_envelope(envelope) == []
    assert envelope["schema_version"] == 1
    assert envelope["report_kind"] == "qre_governed_offline_research_artifact"
    assert envelope["source_mode"] == "offline_fixture"
    assert envelope["inputs"]["dataset_fingerprint"] == "fixture:v1:deterministic"


def test_artifact_contains_ordered_stage_records_evidence_and_disposition() -> None:
    envelope = _envelope()

    assert tuple(record["stage"] for record in envelope["stage_records"]) == dry_run.DRY_RUN_STAGE_ORDER
    assert envelope["evidence_pack"]["complete"] is False
    assert envelope["disposition"]["decision"] == "blocked_before_screening"
    assert envelope["disposition"]["next_action"] == "resolve_blocking_reasons"


def test_artifact_distinguishes_reason_classes_and_memory_feedback() -> None:
    envelope = _envelope()

    assert "evidence_incomplete" in envelope["evidence_pack"]["missing_evidence"]
    assert "data_quality_failed" in envelope["evidence_pack"]["negative_evidence"]
    assert "data_quality_failed" in envelope["evidence_pack"]["data_source_quality_blockers"]
    assert envelope["memory_feedback"]["lessons"]
    assert envelope["operator_trust_summary"]["what_was_tested"] == ["blocked"]
    assert envelope["operator_trust_summary"]["what_failed"] == 1


def test_artifact_denies_all_execution_and_deployment_authority() -> None:
    authority = _envelope()["authority"]

    assert authority["offline_only"] is True
    for key, value in authority.items():
        if key != "offline_only":
            assert value is False


def test_artifact_write_read_and_latest_are_deterministic_and_tmp_path_only(tmp_path: Path) -> None:
    envelope = _envelope()
    run_path, latest_path = artifacts.write_artifact(envelope, tmp_path)

    assert run_path == tmp_path / "run-001.json"
    assert latest_path == tmp_path / "latest.json"
    assert artifacts.read_artifact(run_path) == envelope
    assert run_path.read_text(encoding="utf-8") == latest_path.read_text(encoding="utf-8")
    assert run_path.parent == tmp_path
    assert latest_path.parent == tmp_path


def test_artifact_never_mutates_frozen_outputs(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}

    artifacts.write_artifact(_envelope(), tmp_path)

    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before
