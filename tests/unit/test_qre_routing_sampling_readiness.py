from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from reporting import qre_routing_sampling_readiness as readiness


def _routing_row(
    *,
    candidate_id: str,
    symbol: str,
    state: str,
    score: int,
    reason: str,
    ready: bool,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "preset_id": "preset-a",
        "behavior_family": "trend_pullback",
        "timeframes": ["1d"],
        "routing_readiness_state": state,
        "routing_readiness_score_pct": score,
        "primary_reason_code": reason,
        "routing_ready": ready,
    }


def _sampling_row(
    *,
    candidate_id: str,
    symbol: str,
    state: str,
    score: int,
    reason: str,
    ready: bool,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "preset_id": "preset-a",
        "behavior_family": "trend_pullback",
        "timeframes": ["1d"],
        "sampling_readiness_state": state,
        "sampling_readiness_score_pct": score,
        "primary_reason_code": reason,
        "sampling_ready": ready,
    }


def _reason_record(record_family: str, subject_id: str) -> dict[str, object]:
    return {
        "record_id": f"rr-{record_family}-{subject_id}",
        "record_family": record_family,
        "subject_id": subject_id,
        "reason_codes": ["ok"],
        "evidence_refs": ["research/production_discovery_catalog.py"],
    }


def test_collect_snapshot_fails_closed_when_real_readiness_rows_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        readiness,
        "_research_module",
        lambda name: {
            "research.qre_routing_readiness_from_basket": SimpleNamespace(
                build_routing_readiness_from_basket=lambda **_: {
                    "summary": {"routing_ready_count": 0},
                    "rows": [],
                },
            ),
            "research.qre_sampling_readiness_from_basket": SimpleNamespace(
                build_sampling_readiness_from_basket=lambda **_: {
                    "summary": {"sampling_ready_count": 0},
                    "rows": [],
                },
            ),
            "research.qre_reason_records_v1": SimpleNamespace(
                build_reason_records_snapshot=lambda **_: {
                    "records": [],
                    "meta": {"records_by_surface": {}},
                    "record_kind": "qre_reason_record",
                },
            ),
        }[name],
    )

    report = readiness.collect_snapshot(repo_root=tmp_path)

    assert report["summary"]["routing_candidate_count"] == 0
    assert report["summary"]["sampling_candidate_count"] == 0
    assert (
        report["summary"]["final_recommendation"]
        == "readiness_population_missing_real_evidence"
    )
    assert (
        report["summary"]["exact_next_action"]
        == "materialize_real_basket_readiness_inputs"
    )


def test_collect_snapshot_surfaces_reason_record_gaps_and_materializes_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _routing_write(report, *, repo_root=Path(".")):
        base = repo_root / "logs" / "qre_routing_readiness_from_basket"
        base.mkdir(parents=True, exist_ok=True)
        (base / "latest.json").write_text("{}", encoding="utf-8")
        return {"latest": "logs/qre_routing_readiness_from_basket/latest.json"}

    def _sampling_write(report, *, repo_root=Path(".")):
        base = repo_root / "logs" / "qre_sampling_readiness_from_basket"
        base.mkdir(parents=True, exist_ok=True)
        (base / "latest.json").write_text("{}", encoding="utf-8")
        return {"latest": "logs/qre_sampling_readiness_from_basket/latest.json"}

    monkeypatch.setattr(
        readiness,
        "_research_module",
        lambda name: {
            "research.qre_routing_readiness_from_basket": SimpleNamespace(
                build_routing_readiness_from_basket=lambda **_: {
                    "report_kind": "qre_routing_readiness_from_basket",
                    "summary": {"routing_ready_count": 1},
                    "rows": [
                        _routing_row(
                            candidate_id="cand-1",
                            symbol="AAPL",
                            state="ready",
                            score=97,
                            reason="evidence_ready_for_readonly_routing",
                            ready=True,
                        ),
                        _routing_row(
                            candidate_id="cand-2",
                            symbol="MSFT",
                            state="deferred",
                            score=90,
                            reason="oos_evidence_missing",
                            ready=False,
                        ),
                    ],
                },
                write_outputs=_routing_write,
            ),
            "research.qre_sampling_readiness_from_basket": SimpleNamespace(
                build_sampling_readiness_from_basket=lambda **_: {
                    "report_kind": "qre_sampling_readiness_from_basket",
                    "summary": {"sampling_ready_count": 1},
                    "rows": [
                        _sampling_row(
                            candidate_id="cand-1",
                            symbol="AAPL",
                            state="ready",
                            score=100,
                            reason="sampling_ready_for_readonly_requirements",
                            ready=True,
                        ),
                        _sampling_row(
                            candidate_id="cand-2",
                            symbol="MSFT",
                            state="deferred",
                            score=90,
                            reason="oos_evidence_missing",
                            ready=False,
                        ),
                    ],
                },
                write_outputs=_sampling_write,
            ),
            "research.qre_reason_records_v1": SimpleNamespace(
                build_reason_records_snapshot=lambda **_: {
                    "record_kind": "qre_reason_record",
                    "meta": {"records_by_surface": {"routing_readiness": 1, "sampling_readiness": 2}},
                    "records": [
                        _reason_record("routing_readiness", "cand-1"),
                        _reason_record("sampling_readiness", "cand-1"),
                        _reason_record("sampling_readiness", "cand-2"),
                    ],
                },
            ),
        }[name],
    )

    report = readiness.collect_snapshot(
        repo_root=tmp_path,
        materialize_supporting_outputs=True,
    )

    assert report["summary"]["routing_candidate_count"] == 2
    assert report["summary"]["sampling_candidate_count"] == 2
    assert report["summary"]["shared_ready_count"] == 1
    assert report["summary"]["routing_missing_reason_record_count"] == 1
    assert report["summary"]["sampling_missing_reason_record_count"] == 0
    assert (
        report["summary"]["final_recommendation"]
        == "readiness_population_reason_record_gap"
    )
    assert (
        report["summary"]["exact_next_action"]
        == "repair_reason_record_coverage_before_authority_upgrade"
    )
    assert report["materialized_supporting_outputs"] == {
        "routing_latest": "logs/qre_routing_readiness_from_basket/latest.json",
        "sampling_latest": "logs/qre_sampling_readiness_from_basket/latest.json",
    }


def test_write_outputs_materializes_json_and_doc(tmp_path: Path) -> None:
    report = {
        "summary": {
            "routing_candidate_count": 2,
            "sampling_candidate_count": 2,
            "routing_ready_count": 1,
            "sampling_ready_count": 1,
            "shared_ready_count": 1,
            "routing_reason_record_coverage_pct": 100.0,
            "sampling_reason_record_coverage_pct": 100.0,
            "final_recommendation": "readiness_population_materialized",
            "exact_next_action": "preserve_evidence_backed_ready_and_non_ready_states",
            "routing_state_counts": {"ready": 1, "blocked": 0, "deferred": 1, "fail_closed": 0},
            "sampling_state_counts": {"ready": 1, "blocked": 0, "deferred": 1, "fail_closed": 0},
        },
        "candidate_examples_top": [
            {
                "symbol": "AAPL",
                "preset_id": "preset-a",
                "routing_state": "ready",
                "routing_score_pct": 97,
                "sampling_state": "ready",
                "sampling_score_pct": 100,
                "shared_ready": True,
                "routing_reason_record_present": True,
                "sampling_reason_record_present": True,
                "primary_reasons": ["routing_ready"],
            }
        ],
    }

    paths = readiness.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_routing_sampling_readiness/latest.json"
    assert paths["doc"] == "docs/governance/qre_routing_sampling_readiness.md"
    assert "QRE Routing and Sampling Readiness" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")


def test_module_avoids_static_research_imports() -> None:
    src = Path(readiness.__file__).read_text(encoding="utf-8")
    assert "from research import" not in src
    assert "import research" not in src
