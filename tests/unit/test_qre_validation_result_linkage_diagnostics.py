from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from reporting import qre_validation_result_linkage_diagnostics as diag

FROZEN = "2026-06-01T12:00:00Z"


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_authorities(
    tmp_path: Path,
    *,
    hypothesis_id: str = "qre-hyp-fixture-001",
    candidate_source_id: str = "candidate-001",
    validation_plan_id: str = "qre-plan-fixture-001",
    run_manifest_id: str = "qre-run-fixture-001",
) -> dict[str, Path]:
    hypotheses = _write_json(
        tmp_path / "hypotheses.json",
        {
            "report_kind": "qre_hypothesis_candidates",
            "hypotheses": [
                {
                    "hypothesis_id": hypothesis_id,
                    "source_candidate_id": candidate_source_id,
                    "source_observation_id": "qre-obs-fixture-001",
                    "asset_scope": ["BTC-USD"],
                    "timeframe_scope": ["1h"],
                    "supporting_evidence_refs": [
                        f"research/research_latest.json#{candidate_source_id}"
                    ],
                }
            ],
        },
    )
    plans = _write_json(
        tmp_path / "plans.json",
        {
            "report_kind": "qre_hypothesis_validation_plan",
            "validation_plans": [
                {
                    "hypothesis_id": hypothesis_id,
                    "validation_plan_id": validation_plan_id,
                }
            ],
        },
    )
    manifests = _write_json(
        tmp_path / "run_manifests.json",
        {
            "report_kind": "qre_research_run_manifest",
            "run_manifests": [
                {
                    "run_manifest_id": run_manifest_id,
                    "target_hypothesis_id": hypothesis_id,
                    "target_validation_plan_id": validation_plan_id,
                }
            ],
        },
    )
    return {"hypotheses": hypotheses, "plans": plans, "manifests": manifests}


def _snapshot(tmp_path: Path, sources: list[Path]) -> dict:
    authorities = _write_authorities(tmp_path)
    return diag.collect_snapshot(
        source_artifact_paths=sources,
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
    )


def _source(path: Path, rows: list, **overrides) -> Path:
    payload = {"candidates": rows}
    payload.update(overrides)
    return _write_json(path, payload)


def _assert_safety_flags(snapshot: dict) -> None:
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    for key in (
        "writes_development_work_queue",
        "writes_seed_jsonl",
        "writes_generated_seed_jsonl",
        "writes_research_action_queue",
        "mutates_campaign_queue",
        "mutates_strategy_or_preset",
        "mutates_paper_shadow_live_runtime",
        "launches_codex",
        "eligible_for_direct_execution",
    ):
        assert snapshot[key] is False


def test_missing_sources_fail_closed(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [tmp_path / "missing.json"])

    assert snap["note"] == diag.NOTE_INPUT_ISSUES
    assert snap["counts"]["total_source_rows"] == 0
    assert snap["deterministic_mapping_possible"] is False
    assert (
        f"{diag.NOTE_SOURCE_ABSENT}:{tmp_path.as_posix()}/missing.json"
        in snap["validation_warnings"]
    )
    _assert_safety_flags(snap)


def test_malformed_source_artifacts_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "screening_evidence_latest.v1.json"
    source.write_text("{", encoding="utf-8")

    snap = _snapshot(tmp_path, [source])

    assert snap["note"] == diag.NOTE_INPUT_ISSUES
    assert snap["counts"]["total_source_rows"] == 0
    assert snap["deterministic_mapping_possible"] is False
    assert any(diag.NOTE_SOURCE_UNPARSEABLE in item for item in snap["validation_warnings"])


def test_direct_hypothesis_id_rows_are_classified_linkable(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [{"candidate_id": "row-1", "hypothesis_id": "qre-hyp-fixture-001"}],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["linkable_direct_hypothesis_id"] == 1
    assert snap["counts"]["skipped_unlinked_total"] == 0
    assert snap["deterministic_mapping_possible"] is True


def test_candidate_id_matching_hypothesis_source_ids_is_linkable(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [{"candidate_id": "candidate-001"}],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["linkable_candidate_id_match"] == 1
    assert snap["counts"]["skipped_unlinked_total"] == 0


def test_asset_timeframe_only_rows_are_ambiguous_not_linkable(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [{"asset": "BTC-USD", "timeframe": "1h"}],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["source_asset_timeframe_ambiguous"] == 1
    assert snap["counts"]["by_classification"]["linkable_direct_hypothesis_id"] == 0
    assert snap["counts"]["by_classification"]["linkable_candidate_id_match"] == 0
    assert snap["counts"]["skipped_unlinked_total"] == 1


def test_total_skipped_count_matches_fixture(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [
            {"hypothesis_id": "qre-hyp-fixture-001"},
            {"asset": "BTC-USD", "timeframe": "1h"},
            {"candidate_id": "unknown-candidate"},
            "not-a-dict",
        ],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["total_source_rows"] == 4
    assert snap["counts"]["skipped_unlinked_total"] == 3
    assert snap["counts"]["linkage_complete_total"] == 1


def test_examples_are_bounded(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "unknown_source.json",
        [{"candidate_id": f"unsupported-{index:02d}"} for index in range(25)],
        report_kind="unsupported_fixture",
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["total_source_rows"] == 25
    assert len(snap["skipped_examples"]) == 20
    for example in snap["skipped_examples"]:
        assert set(example["candidate_link_fields"]) <= set(diag.CANDIDATE_LINK_FIELDS)


def test_unsupported_source_schema_is_classified(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "unsupported.json",
        [{"candidate_id": "candidate-001"}],
        report_kind="unsupported_fixture",
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["unsupported_source_schema"] == 1
    assert snap["counts"]["skipped_unlinked_total"] == 1


def test_candidate_id_present_but_not_in_hypotheses(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [{"candidate_id": "missing-candidate"}],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["source_candidate_id_not_in_hypotheses"] == 1
    assert snap["counts"]["skipped_unlinked_total"] == 1


def test_missing_validation_plan_id_classification(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [{"hypothesis_id": "qre-hyp-fixture-001"}],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["missing_validation_plan_id"] == 1
    assert snap["counts"]["by_classification"]["linkable_validation_plan_id_match"] == 1


def test_missing_run_manifest_id_classification(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "screening_evidence_latest.v1.json",
        [
            {
                "hypothesis_id": "qre-hyp-fixture-001",
                "validation_plan_id": "qre-plan-fixture-001",
            }
        ],
    )

    snap = _snapshot(tmp_path, [source])

    assert snap["counts"]["by_classification"]["missing_run_manifest_id"] == 1
    assert snap["counts"]["by_classification"]["linkable_run_manifest_id_match"] == 1


def test_write_outputs_only_allows_diagnostic_latest_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_validation_result_linkage_diagnostics"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(diag, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(diag, "ARTIFACT_LATEST", latest)
    snap = diag.collect_snapshot(
        source_artifact_paths=[],
        hypothesis_artifact_path=tmp_path / "missing-hyp.json",
        plan_artifact_path=tmp_path / "missing-plan.json",
        run_manifest_artifact_path=tmp_path / "missing-run.json",
        generated_at_utc=FROZEN,
    )

    written = diag.write_outputs(snap)

    assert written == latest
    assert latest.exists()
    assert [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json")] == [
        "logs/qre_validation_result_linkage_diagnostics/latest.json"
    ]
    with pytest.raises(ValueError):
        diag.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_forbidden_calls_imports_and_mutating_paths_absent() -> None:
    src = Path(diag.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules: set[str] = set()
    forbidden_runtime_modules = (
        "broker",
        "live",
        "paper",
        "shadow",
        "risk",
        "trading",
        "execution",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                assert (func.value.id, func.attr) != ("os", "system")
                assert func.value.id != "subprocess"

    assert "subprocess" not in imported_modules
    for module in imported_modules:
        root = module.split(".")[0]
        assert root not in forbidden_runtime_modules
    for token in (
        "generated_seed.jsonl",
        "seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "agent/backtesting/strategies.py",
        "registry.py",
    ):
        assert token not in src
