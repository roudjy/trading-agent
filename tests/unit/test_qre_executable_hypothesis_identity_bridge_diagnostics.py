from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from reporting import qre_executable_hypothesis_identity_bridge_diagnostics as diag

FROZEN = "2026-06-01T12:00:00Z"


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_authorities(
    tmp_path: Path,
    hypothesis_ids: list[str],
    *,
    executable_bridge_by_hypothesis_id: dict[str, str] | None = None,
) -> dict[str, Path]:
    bridge = executable_bridge_by_hypothesis_id or {}
    hypotheses = []
    plans = []
    manifests = []
    for index, hypothesis_id in enumerate(hypothesis_ids, start=1):
        plan_id = f"qre-plan-fixture-{index:03d}"
        run_id = f"qre-run-fixture-{index:03d}"
        hypothesis = {"hypothesis_id": hypothesis_id}
        executable_hypothesis_id = bridge.get(hypothesis_id)
        if executable_hypothesis_id:
            hypothesis.update(
                {
                    "executable_hypothesis_id": executable_hypothesis_id,
                    "source_hypothesis_id": f"source-{index:03d}",
                    "strategy_family": "trend",
                    "strategy_template_id": "trend_pullback",
                    "preset_name": f"preset-{index:03d}",
                }
            )
        hypotheses.append(hypothesis)
        plans.append(
            {
                "hypothesis_id": hypothesis_id,
                "validation_plan_id": plan_id,
            }
        )
        manifests.append(
            {
                "run_manifest_id": run_id,
                "target_hypothesis_id": hypothesis_id,
                "target_validation_plan_id": plan_id,
            }
        )
    return {
        "hypotheses": _write_json(
            tmp_path / "hypotheses.json",
            {
                "report_kind": "qre_hypothesis_candidates",
                "hypotheses": hypotheses,
            },
        ),
        "plans": _write_json(
            tmp_path / "plans.json",
            {
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": plans,
            },
        ),
        "manifests": _write_json(
            tmp_path / "run_manifests.json",
            {
                "report_kind": "qre_research_run_manifest",
                "run_manifests": manifests,
            },
        ),
    }


def _preset(
    name: str,
    hypothesis_id: str | None,
    *,
    enabled: bool = True,
    diagnostic_only: bool = False,
    excluded_from_daily_scheduler: bool = False,
    excluded_from_candidate_promotion: bool = False,
    status: str = "stable",
    preset_class: str = "experimental",
) -> dict:
    return {
        "name": name,
        "enabled": enabled,
        "diagnostic_only": diagnostic_only,
        "excluded_from_daily_scheduler": excluded_from_daily_scheduler,
        "excluded_from_candidate_promotion": excluded_from_candidate_promotion,
        "status": status,
        "preset_class": preset_class,
        "hypothesis_id": hypothesis_id,
    }


def _snapshot(
    tmp_path: Path,
    *,
    authority_ids: list[str],
    presets: list[dict],
    executable_bridge_by_hypothesis_id: dict[str, str] | None = None,
) -> dict:
    authorities = _write_authorities(
        tmp_path,
        authority_ids,
        executable_bridge_by_hypothesis_id=executable_bridge_by_hypothesis_id,
    )
    return diag.collect_snapshot(
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
        presets=presets,
    )


def _assert_safety(snapshot: dict) -> None:
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert (
        snapshot["bridge"]["regeneration_linkage_expected"]
        is snapshot["bridge"]["deterministic_mapping_possible"]
    )
    for key in (
        "writes_development_work_queue",
        "writes_seed_jsonl",
        "writes_generated_seed_jsonl",
        "writes_research_action_queue",
        "mutates_campaign_queue",
        "mutates_strategy_or_preset",
        "mutates_research_artifacts",
        "mutates_paper_shadow_live_runtime",
        "launches_codex",
        "eligible_for_direct_execution",
    ):
        assert snapshot[key] is False


def test_current_like_mismatch_reports_bridge_required(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["qre-hyp-04f4d1cd9a515176", "qre-hyp-21f9405cde762bc3"],
        presets=[
            _preset("trend_pullback_crypto_1h", "trend_pullback_v1"),
            _preset(
                "vol_compression_breakout_crypto_1h",
                "volatility_compression_breakout_v0",
            ),
        ],
    )

    assert snap["qre_authority"]["available"] is True
    assert snap["qre_authority"]["linked_exact_ids"] == 2
    assert snap["qre_authority"]["status_counts"] == {"linked_exact_ids": 2}
    assert snap["executable_presets"]["executable_hypothesis_ids"] == [
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    ]
    assert snap["bridge"]["executable_ids_present_in_qre_authority"] == []
    assert snap["bridge"]["executable_ids_missing_from_qre_authority"] == [
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    ]
    assert snap["bridge"]["executable_to_qre_authority_match_count"] == 0
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert snap["bridge"]["deterministic_mapping_possible"] is False
    assert snap["bridge"]["primary_blocker"] == ("executable_hypothesis_id_not_in_qre_authority")
    assert snap["final_recommendation"] == (
        "executable_hypothesis_identity_bridge_required_before_regeneration"
    )
    assert "qre_authority_available" in snap["bridge"]["reason_codes"]
    assert "qre_authority_all_linked_exact_ids" in snap["bridge"]["reason_codes"]
    assert "executable_hypothesis_ids_discovered" in snap["bridge"]["reason_codes"]
    assert (
        "runtime_regeneration_expected_unlinked_unknown_hypothesis_id"
        in snap["bridge"]["reason_codes"]
    )
    assert (
        "deterministic_mapping_not_supported_without_explicit_bridge"
        in snap["bridge"]["reason_codes"]
    )
    _assert_safety(snap)


def test_exact_match_expects_regeneration_linkage(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["trend_pullback_v1", "volatility_compression_breakout_v0"],
        presets=[
            _preset("trend_pullback_crypto_1h", "trend_pullback_v1"),
            _preset(
                "vol_compression_breakout_crypto_1h",
                "volatility_compression_breakout_v0",
            ),
        ],
    )

    assert snap["bridge"]["executable_ids_present_in_qre_authority"] == [
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    ]
    assert snap["bridge"]["executable_ids_missing_from_qre_authority"] == []
    assert snap["bridge"]["executable_to_qre_authority_match_count"] == 2
    assert snap["bridge"]["regeneration_linkage_expected"] is True
    assert snap["bridge"]["deterministic_mapping_possible"] is True
    assert snap["bridge"]["primary_blocker"] == "no_primary_blocker"
    _assert_safety(snap)


def test_explicit_bridge_reports_regeneration_linkage_ready(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["qre-hyp-fixture-001", "qre-hyp-fixture-002"],
        executable_bridge_by_hypothesis_id={
            "qre-hyp-fixture-001": "trend_pullback_v1",
            "qre-hyp-fixture-002": "volatility_compression_breakout_v0",
        },
        presets=[
            _preset("trend_pullback_crypto_1h", "trend_pullback_v1"),
            _preset(
                "vol_compression_breakout_crypto_1h",
                "volatility_compression_breakout_v0",
            ),
        ],
    )

    assert snap["qre_authority"]["executable_bridge_summary"] == {
        "exact_bridge_count": 2,
        "ambiguous_bridge_count": 0,
        "unsafe_bridge_count": 0,
    }
    assert snap["qre_authority"]["sample_executable_hypothesis_ids"] == [
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    ]
    assert snap["bridge"]["executable_ids_missing_from_qre_authority"] == []
    assert snap["bridge"]["regeneration_linkage_expected"] is True
    assert snap["bridge"]["deterministic_mapping_possible"] is True
    assert snap["bridge"]["primary_blocker"] == "no_primary_blocker"
    assert snap["final_recommendation"] == (
        "executable_hypothesis_identity_bridge_ready_for_regeneration"
    )
    assert {
        row["qre_authority_linkage_mode"] for row in snap["executable_presets"]["per_preset"]
    } == {"executable_hypothesis_bridge"}
    _assert_safety(snap)


def test_explicit_bridge_reports_false_when_one_executable_id_is_missing(
    tmp_path: Path,
) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["qre-hyp-fixture-001", "qre-hyp-fixture-002"],
        executable_bridge_by_hypothesis_id={
            "qre-hyp-fixture-001": "trend_pullback_v1",
        },
        presets=[
            _preset("trend_pullback_crypto_1h", "trend_pullback_v1"),
            _preset(
                "vol_compression_breakout_crypto_1h",
                "volatility_compression_breakout_v0",
            ),
        ],
    )

    assert snap["bridge"]["executable_ids_present_in_qre_authority"] == ["trend_pullback_v1"]
    assert snap["bridge"]["executable_ids_missing_from_qre_authority"] == [
        "volatility_compression_breakout_v0"
    ]
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert snap["bridge"]["deterministic_mapping_possible"] is False
    assert snap["bridge"]["primary_blocker"] == "executable_hypothesis_id_not_in_qre_authority"


def test_partial_match_fails_closed_and_reports_missing_id(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["trend_pullback_v1", "qre-hyp-generated"],
        presets=[
            _preset("trend_pullback_crypto_1h", "trend_pullback_v1"),
            _preset(
                "vol_compression_breakout_crypto_1h",
                "volatility_compression_breakout_v0",
            ),
        ],
    )

    assert snap["bridge"]["executable_ids_present_in_qre_authority"] == ["trend_pullback_v1"]
    assert snap["bridge"]["executable_ids_missing_from_qre_authority"] == [
        "volatility_compression_breakout_v0"
    ]
    assert snap["bridge"]["executable_to_qre_authority_match_count"] == 1
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert snap["bridge"]["primary_blocker"] == ("executable_hypothesis_id_not_in_qre_authority")




def test_controlled_validation_bridge_readiness_reports_missing_executable_authority(
    tmp_path: Path,
) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["qre-hyp-04f4d1cd9a515176"],
        presets=[_preset("trend_pullback_equities_4h", "trend_pullback_v1")],
    )

    readiness = snap["controlled_validation_bridge_readiness"]

    assert readiness["ready"] is False
    assert readiness["executable_hypothesis_count"] == 1
    assert readiness["ready_count"] == 0
    assert readiness["blocked_count"] == 1
    assert readiness["rows"] == [
        {
            "preset_name": "trend_pullback_equities_4h",
            "executable_hypothesis_id": "trend_pullback_v1",
            "in_qre_authority": False,
            "qre_authority_linkage_mode": None,
            "qre_authority_status": None,
            "validation_plan_id_present": False,
            "run_manifest_id_present": False,
            "ready": False,
            "primary_blocker": "executable_hypothesis_id_not_in_qre_authority",
        }
    ]
    _assert_safety(snap)


def test_controlled_validation_bridge_readiness_reports_exact_bridge_ready(
    tmp_path: Path,
) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["qre-hyp-fixture-001"],
        executable_bridge_by_hypothesis_id={
            "qre-hyp-fixture-001": "trend_pullback_v1",
        },
        presets=[_preset("trend_pullback_equities_4h", "trend_pullback_v1")],
    )

    readiness = snap["controlled_validation_bridge_readiness"]

    assert readiness["ready"] is True
    assert readiness["executable_hypothesis_count"] == 1
    assert readiness["ready_count"] == 1
    assert readiness["blocked_count"] == 0
    assert readiness["rows"] == [
        {
            "preset_name": "trend_pullback_equities_4h",
            "executable_hypothesis_id": "trend_pullback_v1",
            "in_qre_authority": True,
            "qre_authority_linkage_mode": "executable_hypothesis_bridge",
            "qre_authority_status": "bridge_exact",
            "validation_plan_id_present": True,
            "run_manifest_id_present": True,
            "ready": True,
            "primary_blocker": "no_primary_blocker",
        }
    ]
    _assert_safety(snap)


def test_missing_qre_authority_artifacts_fail_closed(tmp_path: Path) -> None:
    snap = diag.collect_snapshot(
        hypothesis_artifact_path=tmp_path / "missing-hypotheses.json",
        plan_artifact_path=tmp_path / "missing-plans.json",
        run_manifest_artifact_path=tmp_path / "missing-runs.json",
        generated_at_utc=FROZEN,
        presets=[_preset("trend_pullback_crypto_1h", "trend_pullback_v1")],
    )

    assert snap["qre_authority"]["available"] is False
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert snap["bridge"]["deterministic_mapping_possible"] is False
    assert snap["bridge"]["primary_blocker"] == "qre_authority_unavailable"
    assert any("qre_artifact_missing" in item for item in snap["validation_warnings"])
    _assert_safety(snap)


def test_malformed_qre_authority_artifacts_fail_closed(tmp_path: Path) -> None:
    hypotheses = tmp_path / "hypotheses.json"
    hypotheses.write_text("{", encoding="utf-8")
    plans = _write_json(
        tmp_path / "plans.json",
        {"report_kind": "qre_hypothesis_validation_plan", "validation_plans": []},
    )
    manifests = _write_json(
        tmp_path / "run_manifests.json",
        {"report_kind": "qre_research_run_manifest", "run_manifests": []},
    )

    snap = diag.collect_snapshot(
        hypothesis_artifact_path=hypotheses,
        plan_artifact_path=plans,
        run_manifest_artifact_path=manifests,
        generated_at_utc=FROZEN,
        presets=[_preset("trend_pullback_crypto_1h", "trend_pullback_v1")],
    )

    assert snap["qre_authority"]["available"] is False
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert any("qre_artifact_malformed" in item for item in snap["validation_warnings"])


def test_no_executable_hypothesis_ids_fails_closed(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["trend_pullback_v1"],
        presets=[
            _preset("baseline_without_id", None),
            _preset("disabled_with_id", "trend_pullback_v1", enabled=False),
        ],
    )

    assert snap["executable_presets"]["executable_hypothesis_ids"] == []
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert snap["bridge"]["deterministic_mapping_possible"] is False
    assert snap["bridge"]["primary_blocker"] == "no_executable_hypothesis_ids"
    assert "no_executable_hypothesis_ids_discovered" in snap["bridge"]["reason_codes"]


def test_per_preset_rows_are_bounded_and_include_required_fields(tmp_path: Path) -> None:
    presets = [_preset(f"preset-{index:03d}", f"hyp-{index:03d}") for index in range(125)]
    snap = _snapshot(tmp_path, authority_ids=["hyp-000"], presets=presets)

    rows = snap["executable_presets"]["per_preset"]
    assert len(rows) == 100
    assert snap["executable_presets"]["per_preset_truncated"] is True
    required = {
        "preset_name",
        "enabled",
        "diagnostic_only",
        "excluded_from_daily_scheduler",
        "excluded_from_candidate_promotion",
        "status",
        "preset_class",
        "hypothesis_id",
        "hypothesis_id_present_in_qre_authority",
        "qre_authority_status",
        "qre_authority_linkage_mode",
    }
    assert required <= set(rows[0])
    assert rows[0]["hypothesis_id_present_in_qre_authority"] is True
    assert rows[0]["qre_authority_status"] == "linked_exact_ids"


def test_recommended_bridge_keys_present(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        authority_ids=["qre-hyp-generated"],
        presets=[_preset("trend_pullback_crypto_1h", "trend_pullback_v1")],
    )

    assert snap["recommended_bridge_keys"] == [
        "executable_hypothesis_id",
        "qre_hypothesis_id",
        "source_hypothesis_id",
        "strategy_family",
        "strategy_template_id",
        "preset_name",
        "validation_plan_id",
        "run_manifest_id",
    ]


def test_presets_malformed_fails_closed(tmp_path: Path) -> None:
    authorities = _write_authorities(tmp_path, ["trend_pullback_v1"])
    snap = diag.collect_snapshot(
        hypothesis_artifact_path=authorities["hypotheses"],
        plan_artifact_path=authorities["plans"],
        run_manifest_artifact_path=authorities["manifests"],
        generated_at_utc=FROZEN,
        presets="not-a-preset-sequence",
    )

    assert snap["executable_presets"]["executable_hypothesis_ids"] == []
    assert snap["bridge"]["regeneration_linkage_expected"] is False
    assert "presets_unavailable_or_malformed" in snap["validation_warnings"]


def test_presets_source_parser_handles_annotated_presets_assignment(tmp_path: Path) -> None:
    presets_source = tmp_path / "presets.py"
    presets_source.write_text(
        """
PRESETS: tuple[ResearchPreset, ...] = (
    ResearchPreset(
        name="trend_pullback_crypto_1h",
        enabled=True,
        status="stable",
        preset_class="experimental",
        hypothesis_id="trend_pullback_v1",
    ),
)
""",
        encoding="utf-8",
    )

    presets, warnings = diag._presets_from_source(presets_source)

    assert warnings == []
    assert presets == [
        {
            "enabled": True,
            "diagnostic_only": False,
            "excluded_from_daily_scheduler": False,
            "excluded_from_candidate_promotion": False,
            "status": "stable",
            "preset_class": "experimental",
            "hypothesis_id": "trend_pullback_v1",
            "name": "trend_pullback_crypto_1h",
        }
    ]


def test_write_snapshot_only_allows_diagnostic_latest_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_executable_hypothesis_identity_bridge"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(diag, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(diag, "ARTIFACT_LATEST", latest)
    snap = diag.collect_snapshot(
        hypothesis_artifact_path=tmp_path / "missing-hyp.json",
        plan_artifact_path=tmp_path / "missing-plan.json",
        run_manifest_artifact_path=tmp_path / "missing-run.json",
        generated_at_utc=FROZEN,
        presets=[],
    )

    written = diag.write_snapshot(snap)

    assert written == latest
    assert latest.exists()
    assert [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json")] == [
        "logs/qre_executable_hypothesis_identity_bridge/latest.json"
    ]
    with pytest.raises(ValueError):
        diag.write_snapshot(snap, output_path=tmp_path / "outside.json")


def test_main_writes_only_latest_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    authorities = _write_authorities(tmp_path, ["qre-hyp-generated"])
    artifact_dir = tmp_path / "logs" / "qre_executable_hypothesis_identity_bridge"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(diag, "DEFAULT_HYPOTHESIS_ARTIFACT_PATH", authorities["hypotheses"])
    monkeypatch.setattr(diag, "DEFAULT_PLAN_ARTIFACT_PATH", authorities["plans"])
    monkeypatch.setattr(diag, "DEFAULT_RUN_MANIFEST_ARTIFACT_PATH", authorities["manifests"])
    monkeypatch.setattr(diag, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(diag, "ARTIFACT_LATEST", latest)
    monkeypatch.setattr(
        diag,
        "_load_default_presets",
        lambda: ([_preset("trend_pullback_crypto_1h", "trend_pullback_v1")], []),
    )

    assert diag.main(["--frozen-utc", FROZEN]) == 0

    assert latest.exists()
    assert [path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("latest.json")] == [
        "logs/qre_executable_hypothesis_identity_bridge/latest.json"
    ]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["safe_to_execute"] is False
    assert payload["read_only"] is True


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
        "research.run_research",
        "agent/backtesting/strategies.py",
        "registry.py",
        "strategy_matrix.csv",
        "research/research_latest.json",
        "import difflib",
        "SequenceMatcher",
        "fuzzy",
        "levenshtein",
    ):
        assert token not in src
