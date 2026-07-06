from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

import pytest

from reporting import qre_research_supervisor as supervisor


def _configure_paths(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(supervisor, "REPO_ROOT", repo_root)
    monkeypatch.setattr(supervisor, "LEASE_PATH", repo_root / "logs/qre_research_supervisor/lease.json")
    monkeypatch.setattr(supervisor, "STATUS_PATH", repo_root / "logs/qre_research_supervisor/latest.json")
    monkeypatch.setattr(supervisor, "HEALTHCHECK_PATH", repo_root / "logs/qre_research_supervisor/healthcheck.json")
    monkeypatch.setattr(supervisor, "RUNTIME_EPOCH_PATH", repo_root / "generated_research/alpha_discovery/runtime_epoch/latest.json")
    monkeypatch.setattr(supervisor, "SOURCE_QUALIFICATIONS_PATH", repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json")
    monkeypatch.setattr(supervisor, "GAP_REGISTRY_PATH", repo_root / "generated_research/alpha_discovery/capability_gaps/latest.json")
    monkeypatch.setattr(supervisor, "BLOCKED_EXPERIMENTS_PATH", repo_root / "generated_research/alpha_discovery/blocked_experiments/latest.json")


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _generated_artifact_digests(repo_root: Path) -> dict[str, str]:
    root = repo_root / "generated_research"
    return {path.relative_to(root).as_posix(): _file_digest(path) for path in root.rglob("*.json")}


def _write_minimal_legacy_blocked_fixture(
    repo_root: Path,
    *,
    include_hypothesis: bool = True,
    gap_experiment_id: str = "qexp-legacy",
) -> dict[str, str]:
    artifact_root = repo_root / "generated_research/alpha_discovery"
    for relative in (
        "source_qualifications",
        "status",
        "runtime_epoch",
        "runs",
        "blocked_experiments",
        "capability_gaps",
        "search_ledger",
        "hypotheses",
        "experiments",
    ):
        (artifact_root / relative).mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)

    ids = {
        "hypothesis_id": "qah-legacy",
        "experiment_id": "qexp-legacy",
        "gap_id": "qgap-legacy",
        "ledger_id": "qsl-legacy",
        "runtime_epoch_id": "qepoch-legacy",
        "qualification_set_id": "qdsqset-legacy",
        "snapshot_lineage_set_id": "qdsnapset-legacy",
    }
    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": ids["snapshot_lineage_set_id"]}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "qrev-legacy"}),
        encoding="utf-8",
    )
    (artifact_root / "source_qualifications/latest.json").write_text(
        json.dumps(
            {
                "rows": [{"dataset_snapshot_id": "snap-blocked", "allowed_evidence_tier": "SOURCE_BLOCKED", "qualification_status": "BLOCKED"}],
                "content_identity": ids["qualification_set_id"],
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "status/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": ids["runtime_epoch_id"],
                "qualification_set_id": ids["qualification_set_id"],
                "snapshot_lineage_set_id": ids["snapshot_lineage_set_id"],
                "current_dataset_snapshot": None,
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": ids["experiment_id"],
                "current_campaign": None,
                "run_id": "qarr-legacy",
                "terminal_disposition": "STOPPED_SOURCE_CERTIFICATION_BOUNDARY",
                "execution_status": "COMPLETED",
                "scientific_disposition": "NEEDS_MORE_EVIDENCE",
                "evidence_tier_reached": "EMPIRICAL_SCREENING",
                "search_ledger_id": ids["ledger_id"],
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "runtime_epoch/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": ids["runtime_epoch_id"],
                "qualification_set_id": ids["qualification_set_id"],
                "snapshot_lineage_set_id": ids["snapshot_lineage_set_id"],
                "search_ledger_id": ids["ledger_id"],
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "runs/latest.json").write_text(
        json.dumps({"run_id": "qarr-legacy", "search_ledger_id": ids["ledger_id"]}),
        encoding="utf-8",
    )
    (artifact_root / "blocked_experiments/latest.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "experiment_id": ids["experiment_id"],
                        "hypothesis_id": ids["hypothesis_id"],
                        "gap_ids": [ids["gap_id"]],
                        "current_status": "BLOCKED",
                        "resume_token": "qresume-legacy",
                        "next_retry_after_utc": "2026-07-04T12:00:00Z",
                        "content_identity": "qblocked-legacy",
                    }
                ],
                "content_identity": "qblockedset-legacy",
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "capability_gaps/latest.json").write_text(
        json.dumps(
            {
                "rows": [{"gap_id": ids["gap_id"], "experiment_id": gap_experiment_id, "gap_type": "SOURCE_CERTIFICATION_GAP", "status": "WAITING_FOR_OPERATOR"}],
                "content_identity": "qgapset-legacy",
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "search_ledger/latest.json").write_text(
        json.dumps({"ledger": {"search_run_id": ids["ledger_id"]}, "content_identity": "qslc-legacy"}),
        encoding="utf-8",
    )
    (artifact_root / "hypotheses/latest.json").write_text(
        json.dumps({"rows": [{"hypothesis_id": ids["hypothesis_id"]}] if include_hypothesis else [], "content_identity": "qhyp-set"}),
        encoding="utf-8",
    )
    (artifact_root / "experiments/latest.json").write_text(
        json.dumps({"rows": [{"experiment_id": ids["experiment_id"]}], "content_identity": "qexp-set"}),
        encoding="utf-8",
    )
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": ids["runtime_epoch_id"],
                "qualification_set_id": ids["qualification_set_id"],
                "snapshot_lineage_set_id": ids["snapshot_lineage_set_id"],
                "current_dataset_snapshot": None,
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": ids["experiment_id"],
                "current_campaign": None,
                "watermarks": {
                    "snapshot_lineage": ids["snapshot_lineage_set_id"],
                    "source_qualifications": ids["qualification_set_id"],
                    "open_gap_ids": [ids["gap_id"]],
                },
            }
        ),
        encoding="utf-8",
    )
    return ids


def test_supervisor_no_change_skip(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/status").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "snap-a"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-a"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "qual-a"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/status/latest.json").write_text(
        json.dumps({"content_identity": "alpha-a"}),
        encoding="utf-8",
    )
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "watermarks": {
                    "snapshot_lineage": "snap-a",
                    "source_qualifications": "qual-a",
                    "open_gap_ids": [],
                    "alpha_status": "alpha-old",
                },
                "last_successful_cycle": {"run_id": "old-run"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(supervisor, "_open_gaps", lambda: [])
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: [])
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": "snap-a"}, "revisions": {"rows": []}})

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)
    assert payload["current_stage"] == "NO_CHANGE_SKIP"
    assert payload["health"] == "HEALTHY_WAITING_FOR_TRIGGER"


def test_supervisor_epoch_mismatch_blocks_new_work(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/status").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "snap-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "qual-current", "qualification_set_id": "qual-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/status/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-current",
                "qualification_set_id": "qual-current",
                "snapshot_lineage_set_id": "snap-current",
                "current_dataset_snapshot": "snap-qual-1",
                "current_source_tier": "SOURCE_SCREENING_ELIGIBLE",
                "current_experiment": "qexp-current",
                "current_campaign": "qcam-current",
                "run_id": "qarr-current",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-old",
                "qualification_set_id": "qual-old",
                "snapshot_lineage_set_id": "snap-old",
                "current_dataset_snapshot": "snap-old",
                "current_source_tier": "SOURCE_BLOCKED",
                "current_campaign": "qcam-old",
                "watermarks": {
                    "snapshot_lineage": "snap-old",
                    "source_qualifications": "qual-old",
                    "open_gap_ids": [],
                    "alpha_status": "alpha-old",
                },
            }
        ),
        encoding="utf-8",
    )

    called = False

    def _unexpected_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("run_alpha_discovery_mvp should not be called on epoch mismatch")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "_open_gaps", lambda: [])
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: [])
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": "snap-current"}, "revisions": {"rows": []}})

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert called is False
    assert payload["health"] == "DEGRADED_STATE_EPOCH_MISMATCH"
    assert payload["current_stage"] == "DEGRADED_EPOCH_MISMATCH"


def test_supervisor_reconciles_semantically_coherent_epoch_ids(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/status").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "snap-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "dataset_snapshot_id": "snap-qual-1",
                        "allowed_evidence_tier": "SOURCE_BLOCKED",
                        "qualification_status": "BLOCKED",
                    }
                ],
                "content_identity": "qual-current",
                "qualification_set_id": "qual-current",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/status/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-legacy",
                "qualification_set_id": "qual-legacy",
                "snapshot_lineage_set_id": "snap-legacy",
                "current_dataset_snapshot": "snap-qual-1",
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": "qexp-current",
                "current_campaign": None,
                "run_id": "qarr-current",
                "terminal_disposition": "STOPPED_SOURCE_CERTIFICATION_BOUNDARY",
                "execution_status": "COMPLETED",
                "scientific_disposition": "NEEDS_MORE_EVIDENCE",
                "evidence_tier_reached": "EMPIRICAL_SCREENING",
                "search_ledger_id": "qsearch-current",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-legacy",
                "qualification_set_id": "qual-legacy",
                "snapshot_lineage_set_id": "snap-legacy",
                "current_dataset_snapshot": "snap-qual-1",
                "current_source_tier": "SOURCE_BLOCKED",
                "current_campaign": None,
                "watermarks": {
                    "snapshot_lineage": "snap-current",
                    "source_qualifications": "qual-current",
                    "open_gap_ids": ["gap-source"],
                    "alpha_status": "alpha-legacy",
                },
                "last_successful_cycle": {"run_id": "old-run"},
            }
        ),
        encoding="utf-8",
    )

    called = False

    def _unexpected_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("run_alpha_discovery_mvp should not be called for coherent epoch reconciliation")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "_open_gaps", lambda: [{"gap_id": "gap-source", "gap_type": "SOURCE_CERTIFICATION_GAP"}])
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: [])
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": "snap-current"}, "revisions": {"rows": []}})

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert called is False
    assert payload["health"] == "HEALTHY_WAITING_FOR_TRIGGER"
    assert payload["current_stage"] == "COHERENT_EPOCH_RECONCILED"
    assert payload["last_cycle"]["decision"] == "reconciled_semantically_coherent_epoch"
    assert payload["runtime_epoch_id"] != "epoch-legacy"
    assert payload["qualification_set_id"] == "qual-current"
    assert payload["snapshot_lineage_set_id"] == "snap-current"


def test_supervisor_restarted_coherent_state_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/status").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "snap-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").parent.mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps(
            {
                "rows": [{"dataset_snapshot_id": "snap-qual-1", "allowed_evidence_tier": "SOURCE_BLOCKED"}],
                "content_identity": "qual-current",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/status/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-legacy",
                "qualification_set_id": "qual-legacy",
                "snapshot_lineage_set_id": "snap-legacy",
                "current_dataset_snapshot": "snap-qual-1",
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": "qexp-current",
                "current_campaign": None,
                "run_id": "qarr-current",
                "terminal_disposition": "STOPPED_SOURCE_CERTIFICATION_BOUNDARY",
                "execution_status": "COMPLETED",
                "search_ledger_id": "qsearch-current",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-legacy",
                "qualification_set_id": "qual-legacy",
                "snapshot_lineage_set_id": "snap-legacy",
                "current_dataset_snapshot": "snap-qual-1",
                "current_source_tier": "SOURCE_BLOCKED",
                "watermarks": {
                    "snapshot_lineage": "snap-current",
                    "source_qualifications": "qual-current",
                    "open_gap_ids": ["gap-source"],
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(supervisor, "_open_gaps", lambda: [{"gap_id": "gap-source", "gap_type": "SOURCE_CERTIFICATION_GAP"}])
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: [])
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": "snap-current"}, "revisions": {"rows": []}})
    monkeypatch.setattr(
        supervisor,
        "run_alpha_discovery_mvp",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_alpha_discovery_mvp should not be called")),
    )

    first = supervisor.run_cycle(repo_root=repo_root, dry_run=True)
    second = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert first["current_stage"] == "COHERENT_EPOCH_RECONCILED"
    assert second["current_stage"] == "NO_CHANGE_SKIP"
    assert second["health"] == "BLOCKED_SOURCE_CERTIFICATION"


def test_supervisor_blocked_state_skips_repeated_discovery_cycles(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    artifact_root = repo_root / "generated_research/alpha_discovery"
    for relative in (
        "observations",
        "source_qualifications",
        "source_resolution",
        "status",
        "runtime_epoch",
        "runs",
        "blocked_experiments",
        "capability_gaps",
        "search_ledger",
        "hypotheses",
        "critiques",
        "rewrites",
        "scorecards",
        "experiments",
        "strategies",
        "requirements",
        "universe_plans",
        "acquisitions",
        "throughput",
        "alignments",
        "admissions",
        "data_plans",
        "views",
    ):
        (artifact_root / relative).mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)

    hypothesis_id = "qah-baseline"
    experiment_id = "qexp-baseline"
    gap_id = "qgap-baseline"
    search_ledger_id = "qsl-baseline"
    runtime_epoch_id = "qepoch-baseline"
    qualification_set_id = "qdsqset-baseline"
    snapshot_lineage_set_id = "qdsnapset-baseline"
    blocked_retry = "2026-07-04T12:00:00Z"

    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": snapshot_lineage_set_id}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-current"}),
        encoding="utf-8",
    )
    (artifact_root / "source_qualifications/latest.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "dataset_snapshot_id": "snap-blocked",
                        "allowed_evidence_tier": "SOURCE_BLOCKED",
                        "qualification_status": "BLOCKED",
                    }
                ],
                "content_identity": qualification_set_id,
                "qualification_set_id": qualification_set_id,
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "status/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "qepoch-legacy",
                "qualification_set_id": "qdsqset-legacy",
                "snapshot_lineage_set_id": "qdsnapset-legacy",
                "current_dataset_snapshot": None,
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": experiment_id,
                "current_campaign": None,
                "run_id": "qarr-baseline",
                "terminal_disposition": "STOPPED_SOURCE_CERTIFICATION_BOUNDARY",
                "execution_status": "COMPLETED",
                "scientific_disposition": "NEEDS_MORE_EVIDENCE",
                "evidence_tier_reached": "EMPIRICAL_SCREENING",
                "search_ledger_id": search_ledger_id,
                "selected_hypothesis_id": hypothesis_id,
                "requested_execution_tier": "EMPIRICAL_SCREENING",
                "admitted_execution_tier": "COMPILER_ONLY",
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "runtime_epoch/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": runtime_epoch_id,
                "qualification_set_id": qualification_set_id,
                "snapshot_lineage_set_id": snapshot_lineage_set_id,
                "search_ledger_id": search_ledger_id,
                "content_identity": "qepochstate-legacy",
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "runs/latest.json").write_text(
        json.dumps({"run_id": "qarr-baseline", "search_ledger_id": search_ledger_id}),
        encoding="utf-8",
    )
    (artifact_root / "blocked_experiments/latest.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "experiment_id": experiment_id,
                        "hypothesis_id": hypothesis_id,
                        "strategy_spec_id": "qspec-baseline",
                        "preregistration_id": experiment_id,
                        "blocked_stage": "EXECUTE",
                        "gap_ids": [gap_id],
                        "required_data_snapshot": None,
                        "required_source_tier": "SOURCE_SCREENING_ELIGIBLE",
                        "required_primitive": None,
                        "required_executor": None,
                        "current_status": "BLOCKED",
                        "resume_token": "qresume-baseline",
                        "last_attempt_at_utc": "2026-07-04T11:45:00Z",
                        "next_retry_after_utc": blocked_retry,
                        "content_identity": "qblocked-baseline",
                    }
                ],
                "content_identity": "qblockedset-baseline",
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "capability_gaps/latest.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "gap_id": gap_id,
                        "experiment_id": experiment_id,
                        "gap_type": "SOURCE_CERTIFICATION_GAP",
                        "status": "WAITING_FOR_OPERATOR",
                        "request_id": None,
                    }
                ],
                "content_identity": "qgapset-baseline",
            }
        ),
        encoding="utf-8",
    )
    (artifact_root / "search_ledger/latest.json").write_text(
        json.dumps({"ledger": {"search_run_id": search_ledger_id}, "content_identity": "qslc-baseline"}),
        encoding="utf-8",
    )
    (artifact_root / "hypotheses/latest.json").write_text(
        json.dumps({"rows": [{"hypothesis_id": hypothesis_id}], "content_identity": "qhyp-set"}),
        encoding="utf-8",
    )
    (artifact_root / "experiments/latest.json").write_text(
        json.dumps({"rows": [{"experiment_id": experiment_id}], "content_identity": "qexp-set"}),
        encoding="utf-8",
    )
    for relative in (
        "observations/latest.json",
        "critiques/latest.json",
        "rewrites/latest.json",
        "scorecards/latest.json",
        "strategies/latest.json",
        "requirements/latest.json",
        "universe_plans/latest.json",
        "acquisitions/latest.json",
        "throughput/latest.json",
        "alignments/latest.json",
        "admissions/latest.json",
        "data_plans/latest.json",
        "data_plans/coverage_latest.json",
        "source_resolution/latest.json",
        "views/discovery_latest.json",
        "views/validation_latest.json",
        "views/locked_oos_latest.json",
    ):
        path = artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"content_identity": f"fixture-{relative}"}), encoding="utf-8")
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "qepoch-legacy",
                "qualification_set_id": "qdsqset-legacy",
                "snapshot_lineage_set_id": "qdsnapset-legacy",
                "current_dataset_snapshot": None,
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": experiment_id,
                "current_campaign": None,
                "watermarks": {
                    "snapshot_lineage": snapshot_lineage_set_id,
                    "source_qualifications": qualification_set_id,
                    "open_gap_ids": [gap_id],
                },
            }
        ),
        encoding="utf-8",
    )
    open_gaps = [{"gap_id": gap_id, "experiment_id": experiment_id, "gap_type": "SOURCE_CERTIFICATION_GAP", "status": "WAITING_FOR_OPERATOR", "request_id": None}]
    blocked_rows = [
        {
            "experiment_id": experiment_id,
            "hypothesis_id": hypothesis_id,
            "strategy_spec_id": "qspec-baseline",
            "preregistration_id": experiment_id,
            "blocked_stage": "EXECUTE",
            "gap_ids": [gap_id],
            "required_data_snapshot": None,
            "required_source_tier": "SOURCE_SCREENING_ELIGIBLE",
            "required_primitive": None,
            "required_executor": None,
            "current_status": "BLOCKED",
            "resume_token": "qresume-baseline",
            "last_attempt_at_utc": "2026-07-04T11:45:00Z",
            "next_retry_after_utc": blocked_retry,
            "content_identity": "qblocked-baseline",
        }
    ]

    artifact_paths = {
        "observations": artifact_root / "observations/latest.json",
        "hypotheses": artifact_root / "hypotheses/latest.json",
        "critiques": artifact_root / "critiques/latest.json",
        "rewrites": artifact_root / "rewrites/latest.json",
        "scorecards": artifact_root / "scorecards/latest.json",
        "experiments": artifact_root / "experiments/latest.json",
        "strategies": artifact_root / "strategies/latest.json",
        "requirements": artifact_root / "requirements/latest.json",
        "universe_plans": artifact_root / "universe_plans/latest.json",
        "acquisitions": artifact_root / "acquisitions/latest.json",
        "throughput": artifact_root / "throughput/latest.json",
        "alignments": artifact_root / "alignments/latest.json",
        "admissions": artifact_root / "admissions/latest.json",
        "data_plans": artifact_root / "data_plans/latest.json",
        "coverage": artifact_root / "data_plans/coverage_latest.json",
        "capability_gaps": artifact_root / "capability_gaps/latest.json",
        "search_ledger": artifact_root / "search_ledger/latest.json",
        "source_qualifications": artifact_root / "source_qualifications/latest.json",
        "source_resolution": artifact_root / "source_resolution/latest.json",
        "runtime_epoch": artifact_root / "runtime_epoch/latest.json",
        "runs": artifact_root / "runs/latest.json",
        "status": artifact_root / "status/latest.json",
        "discovery_view": artifact_root / "views/discovery_latest.json",
        "validation_view": artifact_root / "views/validation_latest.json",
        "locked_oos_view": artifact_root / "views/locked_oos_latest.json",
    }

    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called for unchanged blocked state")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": snapshot_lineage_set_id}, "revisions": {"rows": []}})
    monkeypatch.setattr(supervisor, "_open_gaps", lambda: list(open_gaps))
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: list(blocked_rows))
    monkeypatch.setattr(
        supervisor,
        "_utcnow",
        iter(
            [
                "2026-07-04T11:56:00Z",
                "2026-07-04T11:56:01Z",
                "2026-07-04T12:01:33Z",
                "2026-07-04T12:01:34Z",
                "2026-07-04T12:06:33Z",
                "2026-07-04T12:06:34Z",
            ]
        ).__next__,
    )

    pre_baseline_digests = {name: _file_digest(path) for name, path in artifact_paths.items()}
    pre_baseline_mtimes = {name: os.stat(path).st_mtime_ns for name, path in artifact_paths.items()}

    baseline = supervisor.run_cycle(repo_root=repo_root, dry_run=True)
    cycle_2 = supervisor.run_cycle(repo_root=repo_root, dry_run=True)
    restart_cycle = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert baseline["current_stage"] == "LEGACY_SEMANTIC_IDENTITY_MIGRATED"
    assert baseline["last_cycle"]["decision"] == "semantic_identity_backfilled_no_change"
    assert baseline["search_ledger_id"] == search_ledger_id
    assert cycle_2["current_stage"] == "NO_CHANGE_SKIP"
    assert restart_cycle["current_stage"] == "NO_CHANGE_SKIP"
    assert cycle_2["health"] == "BLOCKED_SOURCE_CERTIFICATION"
    assert restart_cycle["health"] == "BLOCKED_SOURCE_CERTIFICATION"
    assert cycle_2["last_cycle"]["decision"] == "no_material_change"
    assert restart_cycle["last_cycle"]["decision"] == "no_material_change"
    assert cycle_2["current_campaign"] is None
    assert restart_cycle["current_campaign"] is None
    assert cycle_2["current_dataset_snapshot"] is None
    assert restart_cycle["current_dataset_snapshot"] is None
    assert cycle_2["active_ADE_requests"] == ()
    assert restart_cycle["active_ADE_requests"] == ()
    assert cycle_2["current_experiment"] == experiment_id
    assert restart_cycle["current_experiment"] == experiment_id
    assert cycle_2["search_ledger_id"] == search_ledger_id
    assert restart_cycle["search_ledger_id"] == search_ledger_id
    assert cycle_2["qualification_set_id"] == qualification_set_id
    assert restart_cycle["qualification_set_id"] == qualification_set_id
    assert cycle_2["snapshot_lineage_set_id"] == snapshot_lineage_set_id
    assert restart_cycle["snapshot_lineage_set_id"] == snapshot_lineage_set_id
    assert cycle_2["runtime_epoch_id"] == baseline["runtime_epoch_id"]
    assert restart_cycle["runtime_epoch_id"] == baseline["runtime_epoch_id"]
    assert baseline["semantic_input_identity"].startswith("qsupsem_")
    assert cycle_2["semantic_input_identity"] == baseline["semantic_input_identity"]
    assert restart_cycle["semantic_input_identity"] == baseline["semantic_input_identity"]
    assert cycle_2["blocked_experiments"][0]["experiment_id"] == experiment_id
    assert restart_cycle["blocked_experiments"][0]["experiment_id"] == experiment_id
    assert run_calls == 0
    for name, path in artifact_paths.items():
        assert _file_digest(path) == pre_baseline_digests[name], name
        assert os.stat(path).st_mtime_ns == pre_baseline_mtimes[name], name


def test_supervisor_reconstructs_legacy_ledger_when_status_projection_lost_it(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root)

    status_path = repo_root / "generated_research/alpha_discovery/status/latest.json"
    alpha_status = json.loads(status_path.read_text(encoding="utf-8"))
    alpha_status["search_ledger_id"] = None
    status_path.write_text(json.dumps(alpha_status), encoding="utf-8")

    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called for coherent legacy status repair")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(
        supervisor,
        "_utcnow",
        iter(["2026-07-04T12:03:00Z", "2026-07-04T12:03:01Z"]).__next__,
    )

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["current_stage"] == "LEGACY_SEMANTIC_IDENTITY_MIGRATED"
    assert payload["last_cycle"]["decision"] == "semantic_identity_backfilled_no_change"
    assert payload["search_ledger_id"] == ids["ledger_id"]


def test_supervisor_legacy_ledger_runtime_and_run_consistency_projects_id(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root)

    status_path = repo_root / "generated_research/alpha_discovery/status/latest.json"
    alpha_status = json.loads(status_path.read_text(encoding="utf-8"))
    alpha_status["search_ledger_id"] = None
    status_path.write_text(json.dumps(alpha_status), encoding="utf-8")
    artifact_digests = _generated_artifact_digests(repo_root)
    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called for consistent legacy ledger reconstruction")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(supervisor, "_utcnow", iter(["2026-07-04T12:04:00Z", "2026-07-04T12:04:01Z"]).__next__)

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["current_stage"] == "LEGACY_SEMANTIC_IDENTITY_MIGRATED"
    assert payload["search_ledger_id"] == ids["ledger_id"]
    assert _generated_artifact_digests(repo_root) == artifact_digests


def test_supervisor_legacy_ledger_runtime_run_conflict_fails_closed(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root)
    (repo_root / "generated_research/alpha_discovery/runs/latest.json").write_text(
        json.dumps({"run_id": "qarr-legacy", "search_ledger_id": "qsl-conflicting-run"}),
        encoding="utf-8",
    )
    artifact_digests = _generated_artifact_digests(repo_root)
    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called for conflicting legacy ledger identities")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(supervisor, "_utcnow", iter(["2026-07-04T12:05:00Z", "2026-07-04T12:05:01Z"]).__next__)

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["health"] == "DEGRADED_LEGACY_STATE_INCONSISTENT"
    assert payload["last_cycle"]["reason_codes"] == ("legacy_search_ledger_identity_mismatch",)
    assert payload["operator_actions"] == ("repair_legacy_supervisor_state",)
    assert payload["search_ledger_id"] is None
    assert _generated_artifact_digests(repo_root) == artifact_digests


def test_supervisor_legacy_ledger_runtime_id_survives_missing_ledger_artifact(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root)
    (repo_root / "generated_research/alpha_discovery/search_ledger/latest.json").unlink()
    artifact_digests = _generated_artifact_digests(repo_root)
    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called when optional ledger artifact is absent")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(supervisor, "_utcnow", iter(["2026-07-04T12:06:00Z", "2026-07-04T12:06:01Z"]).__next__)

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["current_stage"] == "LEGACY_SEMANTIC_IDENTITY_MIGRATED"
    assert payload["search_ledger_id"] == ids["ledger_id"]
    assert _generated_artifact_digests(repo_root) == artifact_digests


def test_supervisor_legacy_ledger_artifact_mismatch_fails_closed(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root)
    (repo_root / "generated_research/alpha_discovery/search_ledger/latest.json").write_text(
        json.dumps({"ledger": {"search_run_id": "qsl-conflicting-artifact"}, "content_identity": "qslc-conflicting"}),
        encoding="utf-8",
    )
    artifact_digests = _generated_artifact_digests(repo_root)
    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called for conflicting ledger artifact")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(supervisor, "_utcnow", iter(["2026-07-04T12:07:00Z", "2026-07-04T12:07:01Z"]).__next__)

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["health"] == "DEGRADED_LEGACY_STATE_INCONSISTENT"
    assert payload["last_cycle"]["reason_codes"] == ("legacy_search_ledger_identity_mismatch",)
    assert payload["operator_actions"] == ("repair_legacy_supervisor_state",)
    assert payload["search_ledger_id"] is None
    assert _generated_artifact_digests(repo_root) == artifact_digests


def test_supervisor_legacy_ledgerless_state_remains_ledgerless(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root)
    for relative in (
        "generated_research/alpha_discovery/status/latest.json",
        "generated_research/alpha_discovery/runtime_epoch/latest.json",
        "generated_research/alpha_discovery/runs/latest.json",
    ):
        path = repo_root / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["search_ledger_id"] = None
        path.write_text(json.dumps(payload), encoding="utf-8")
    (repo_root / "generated_research/alpha_discovery/search_ledger/latest.json").write_text(
        json.dumps({"ledger": None, "content_identity": "qslc-ledgerless"}),
        encoding="utf-8",
    )
    artifact_digests = _generated_artifact_digests(repo_root)
    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not be called for legitimate ledgerless legacy state")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(supervisor, "_utcnow", iter(["2026-07-04T12:08:00Z", "2026-07-04T12:08:01Z"]).__next__)

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["current_stage"] == "LEGACY_SEMANTIC_IDENTITY_MIGRATED"
    assert payload["search_ledger_id"] is None
    assert _generated_artifact_digests(repo_root) == artifact_digests


def test_supervisor_incomplete_legacy_state_fails_closed_without_discovery(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root, include_hypothesis=False)

    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not repair incomplete legacy state")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(
        supervisor,
        "_utcnow",
        iter(["2026-07-04T12:01:00Z", "2026-07-04T12:01:01Z"]).__next__,
    )

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["health"] == "DEGRADED_LEGACY_STATE_INCOMPLETE"
    assert payload["current_stage"] == "DEGRADED_LEGACY_STATE_INCOMPLETE"
    assert payload["last_cycle"]["decision"] == "fail_closed_legacy_state_not_migrated"
    assert "legacy_hypotheses_missing" in payload["last_cycle"]["reason_codes"]
    assert "semantic_input_identity" not in payload
    assert payload["operator_actions"] == ("repair_legacy_supervisor_state",)


def test_supervisor_inconsistent_legacy_state_fails_closed_without_discovery(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)
    ids = _write_minimal_legacy_blocked_fixture(repo_root, gap_experiment_id="qexp-other")

    run_calls = 0

    def _unexpected_run(*args, **kwargs):
        nonlocal run_calls
        run_calls += 1
        raise AssertionError("run_alpha_discovery_mvp should not repair inconsistent legacy state")

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _unexpected_run)
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": ids["snapshot_lineage_set_id"]}, "revisions": {"rows": []}})
    monkeypatch.setattr(
        supervisor,
        "_utcnow",
        iter(["2026-07-04T12:02:00Z", "2026-07-04T12:02:01Z"]).__next__,
    )

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 0
    assert payload["health"] == "DEGRADED_LEGACY_STATE_INCONSISTENT"
    assert payload["current_stage"] == "DEGRADED_LEGACY_STATE_INCONSISTENT"
    assert payload["last_cycle"]["decision"] == "fail_closed_legacy_state_not_migrated"
    assert "legacy_gap_experiment_mismatch" in payload["last_cycle"]["reason_codes"]
    assert "semantic_input_identity" not in payload
    assert payload["operator_actions"] == ("repair_legacy_supervisor_state",)


def test_supervisor_run_status_aligns_watermarks_with_run_ids(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/status").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/runtime_epoch").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)

    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "snap-before"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-before"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "qual-before", "qualification_set_id": "qual-before"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/status/latest.json").write_text(
        json.dumps({"content_identity": "alpha-before"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(supervisor, "_open_gaps", lambda: [{"gap_id": "gap-source", "gap_type": "SOURCE_CERTIFICATION_GAP"}])
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: [{"experiment_id": "qexp-run", "content_identity": "qblocked-run", "resume_token": "qresume-run"}])
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": "snap-before"}, "revisions": {"rows": []}})
    monkeypatch.setattr(
        supervisor,
        "run_alpha_discovery_mvp",
        lambda **kwargs: {
            "run_id": "qarr-run",
            "terminal_disposition": "STOPPED_SOURCE_CERTIFICATION_BOUNDARY",
            "execution_status": "COMPLETED",
            "current_dataset_snapshot": None,
            "current_source_tier": "SOURCE_BLOCKED",
            "current_experiment": "qexp-run",
            "current_campaign": None,
            "runtime_epoch_id": "qepoch-run",
            "qualification_set_id": "qual-after",
            "snapshot_lineage_set_id": "snap-after",
            "search_ledger_id": "qsl-run",
            "requested_execution_tier": "EMPIRICAL_SCREENING",
            "admitted_execution_tier": "COMPILER_ONLY",
            "scientific_disposition": "NEEDS_MORE_EVIDENCE",
            "evidence_tier_reached": "EMPIRICAL_SCREENING",
            "content_identity": "qarrc-run",
        },
    )

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert payload["qualification_set_id"] == "qual-after"
    assert payload["watermarks"]["source_qualifications"] == "qual-after"
    assert payload["snapshot_lineage_set_id"] == "snap-after"
    assert payload["watermarks"]["snapshot_lineage"] == "snap-after"


def test_supervisor_source_qualification_change_triggers_material_cycle(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    _configure_paths(monkeypatch, repo_root)

    (repo_root / "generated_research/data_catalog/snapshot_lineage").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/data_catalog/revisions").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/source_qualifications").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/status").mkdir(parents=True, exist_ok=True)
    (repo_root / "generated_research/alpha_discovery/runtime_epoch").mkdir(parents=True, exist_ok=True)
    (repo_root / "logs/qre_research_supervisor").mkdir(parents=True, exist_ok=True)

    (repo_root / "generated_research/data_catalog/snapshot_lineage/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "snap-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/data_catalog/revisions/latest.json").write_text(
        json.dumps({"rows": [], "content_identity": "rev-current"}),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "dataset_snapshot_id": "snap-screening",
                        "allowed_evidence_tier": "SOURCE_SCREENING_ELIGIBLE",
                        "qualification_status": "COHERENT",
                    }
                ],
                "content_identity": "qual-new",
                "qualification_set_id": "qual-new",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "generated_research/alpha_discovery/status/latest.json").write_text(
        json.dumps(
            {
                "runtime_epoch_id": "epoch-old",
                "qualification_set_id": "qual-old",
                "snapshot_lineage_set_id": "snap-current",
                "current_dataset_snapshot": None,
                "current_source_tier": "SOURCE_BLOCKED",
                "current_experiment": None,
                "current_campaign": None,
                "run_id": "qarr-old",
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "logs/qre_research_supervisor/latest.json").write_text(
        json.dumps(
            {
                "semantic_input_identity": "qsupsem-old",
                "watermarks": {
                    "snapshot_lineage": "snap-current",
                    "source_qualifications": "qual-old",
                    "open_gap_ids": [],
                },
                "runtime_epoch_id": "epoch-old",
                "qualification_set_id": "qual-old",
                "snapshot_lineage_set_id": "snap-current",
            }
        ),
        encoding="utf-8",
    )

    run_calls = 0

    def _run_once(**kwargs):
        nonlocal run_calls
        run_calls += 1
        return {
            "run_id": "qarr-new",
            "terminal_disposition": "STOPPED_SOURCE_CERTIFICATION_BOUNDARY",
            "execution_status": "COMPLETED",
            "current_dataset_snapshot": "snap-screening",
            "current_source_tier": "SOURCE_SCREENING_ELIGIBLE",
            "current_experiment": None,
            "current_campaign": None,
            "runtime_epoch_id": "epoch-new",
            "qualification_set_id": "qual-new",
            "snapshot_lineage_set_id": "snap-current",
            "search_ledger_id": "qsl-new",
            "requested_execution_tier": "EMPIRICAL_SCREENING",
            "admitted_execution_tier": "COMPILER_ONLY",
            "scientific_disposition": "NEEDS_MORE_EVIDENCE",
            "evidence_tier_reached": "EMPIRICAL_SCREENING",
            "content_identity": "qarrc-new",
        }

    monkeypatch.setattr(supervisor, "run_alpha_discovery_mvp", _run_once)
    monkeypatch.setattr(supervisor, "_open_gaps", lambda: [])
    monkeypatch.setattr(supervisor, "_blocked_experiments", lambda: [])
    monkeypatch.setattr(supervisor, "load_snapshot_lineage", lambda repo_root: {"snapshot_lineage": {"content_identity": "snap-current"}, "revisions": {"rows": []}})

    payload = supervisor.run_cycle(repo_root=repo_root, dry_run=True)

    assert run_calls == 1
    assert payload["current_stage"] == "COMPLETE"
    assert payload["current_source_tier"] == "SOURCE_SCREENING_ELIGIBLE"
    assert payload["current_campaign"] is None
    assert payload["active_ADE_requests"] == ()
    assert payload["qualification_set_id"] == "qual-new"
    assert payload["watermarks"]["source_qualifications"] == "qual-new"


@pytest.mark.parametrize(
    ("health", "expected_exit"),
    [
        ("HEALTHY_WAITING_FOR_TRIGGER", 0),
        ("BLOCKED_SOURCE_CERTIFICATION", 0),
        ("DEGRADED_STATE_EPOCH_MISMATCH", 1),
    ],
)
def test_supervisor_healthcheck_exit_codes(monkeypatch, tmp_path: Path, health: str, expected_exit: int) -> None:
    healthcheck_path = tmp_path / "logs/qre_research_supervisor/healthcheck.json"
    healthcheck_path.parent.mkdir(parents=True, exist_ok=True)
    healthcheck_path.write_text(json.dumps({"health": health}), encoding="utf-8")
    monkeypatch.setattr(supervisor, "HEALTHCHECK_PATH", healthcheck_path)

    assert supervisor.main(["--healthcheck"]) == expected_exit
