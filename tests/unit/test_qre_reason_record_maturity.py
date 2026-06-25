from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from reporting import qre_reason_record_maturity as maturity


def _reason_record(
    *,
    record_id: str,
    subject_id: str,
    evidence_refs: list[str],
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "record_family": "routing_readiness",
        "subject_id": subject_id,
        "reason_codes": ["routing_ready"],
        "reason_text": "Routing readiness exists.",
        "evidence_refs": evidence_refs,
        "inputs_digest": f"digest-{record_id}",
    }


def test_collect_snapshot_fails_closed_when_records_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        maturity,
        "_research_module",
        lambda name: {
            "research.qre_reason_records_v1": SimpleNamespace(
                build_reason_records_snapshot=lambda **_: {
                    "meta": {"records_by_surface": {}},
                    "records": [],
                },
            ),
            "research.qre_reason_record_audit": SimpleNamespace(
                build_reason_record_audit=lambda **_: {
                    "summary": {
                        "reason_records_manifest_total": 0,
                        "reason_record_coverage_pct": None,
                    },
                    "producer_rows": [],
                },
                write_outputs=lambda report, repo_root=Path("."): {
                    "latest": "logs/qre_reason_record_audit/latest.json",
                },
            ),
            "research.qre_reason_record_normalization": SimpleNamespace(
                build_reason_record_normalization=lambda **_: {
                    "summary": {
                        "reason_record_normalization_ready": False,
                        "invalid_record_count": 0,
                        "producer_gap_count": 0,
                    },
                    "producer_rows": [],
                    "normalized_records": [],
                },
                write_outputs=lambda report, repo_root=Path("."): {
                    "latest": "logs/qre_reason_record_normalization/latest.json",
                },
            ),
        }[name],
    )

    report = maturity.collect_snapshot(repo_root=tmp_path)

    assert report["summary"]["record_count"] == 0
    assert (
        report["summary"]["final_recommendation"]
        == "reason_record_maturity_missing_real_evidence_records"
    )
    assert (
        report["summary"]["exact_next_action"]
        == "materialize_reason_records_from_real_evidence"
    )


def test_collect_snapshot_surfaces_durability_linkage_and_contract_gaps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    evidence_path = tmp_path / "logs" / "qre_inputs" / "source.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text('{"ok": true}\n', encoding="utf-8")

    def _rr_write(snapshot, *, repo_root=Path("."), output_dir=Path("logs/qre_reason_records")):
        base = repo_root / output_dir
        base.mkdir(parents=True, exist_ok=True)
        (base / "latest.jsonl").write_text('{"record_id":"rr1"}\n', encoding="utf-8")
        (base / "latest.meta.json").write_text(
            json.dumps({"total_records": 2}),
            encoding="utf-8",
        )
        return {
            "latest_jsonl": "logs/qre_reason_records/latest.jsonl",
            "latest_meta": "logs/qre_reason_records/latest.meta.json",
        }

    def _audit_write(report, *, repo_root=Path(".")):
        base = repo_root / "logs" / "qre_reason_record_audit"
        base.mkdir(parents=True, exist_ok=True)
        (base / "latest.json").write_text(json.dumps(report), encoding="utf-8")
        return {"latest": "logs/qre_reason_record_audit/latest.json"}

    def _norm_write(report, *, repo_root=Path(".")):
        base = repo_root / "logs" / "qre_reason_record_normalization"
        base.mkdir(parents=True, exist_ok=True)
        (base / "latest.json").write_text(json.dumps(report), encoding="utf-8")
        return {"latest": "logs/qre_reason_record_normalization/latest.json"}

    monkeypatch.setattr(
        maturity,
        "_research_module",
        lambda name: {
            "research.qre_reason_records_v1": SimpleNamespace(
                build_reason_records_snapshot=lambda **_: {
                    "meta": {"records_by_surface": {"routing_readiness": 2}},
                    "records": [
                        _reason_record(
                            record_id="rr1",
                            subject_id="cand-1",
                            evidence_refs=["logs/qre_inputs/source.json"],
                        ),
                        _reason_record(
                            record_id="rr2",
                            subject_id="cand-2",
                            evidence_refs=["logs/qre_inputs/missing.json"],
                        ),
                    ],
                },
                write_outputs=_rr_write,
            ),
            "research.qre_reason_record_audit": SimpleNamespace(
                build_reason_record_audit=lambda **_: {
                    "summary": {
                        "reason_records_manifest_total": 2,
                        "reason_record_coverage_pct": 50.0,
                    },
                    "producer_rows": [
                        {
                            "producer_id": "routing_readiness_from_basket",
                            "status": "coverage_partial",
                            "expected_subject_count": 2,
                            "subjects_with_evidence_refs": 1,
                        }
                    ],
                },
                write_outputs=_audit_write,
            ),
            "research.qre_reason_record_normalization": SimpleNamespace(
                build_reason_record_normalization=lambda **_: {
                    "summary": {
                        "reason_record_normalization_ready": True,
                        "invalid_record_count": 1,
                        "producer_gap_count": 1,
                    },
                    "producer_rows": [
                        {
                            "producer_id": "qre_reason_records_v1",
                            "record_count": 2,
                            "valid_record_count": 1,
                            "invalid_record_count": 1,
                            "status": "normalized_with_contract_gaps",
                            "top_rejection_reasons": {"missing_consumer_refs": 1},
                        }
                    ],
                    "normalized_records": [
                        {
                            "contract_validation": {
                                "rejection_reasons": ["missing_consumer_refs"]
                            }
                        }
                    ],
                },
                write_outputs=_norm_write,
            ),
        }[name],
    )

    report = maturity.collect_snapshot(
        repo_root=tmp_path,
        materialize_supporting_outputs=True,
    )

    assert report["summary"]["record_count"] == 2
    assert report["summary"]["durable_artifact_missing_count"] == 0
    assert report["summary"]["linked_record_count"] == 1
    assert report["summary"]["invalid_record_count"] == 1
    assert (
        report["summary"]["final_recommendation"]
        == "reason_record_maturity_unlinked_evidence"
    )
    assert (
        report["summary"]["exact_next_action"]
        == "repair_missing_evidence_refs_before_authority_upgrade"
    )
    assert report["contract_gap_counts"] == {"missing_consumer_refs": 1}
    assert report["linkage_examples_top"][0]["missing_paths"] == [
        "logs/qre_inputs/missing.json"
    ]


def test_write_outputs_materializes_json_and_doc(tmp_path: Path) -> None:
    report = {
        "summary": {
            "record_count": 1,
            "linked_record_count": 1,
            "invalid_record_count": 0,
            "durable_artifact_missing_count": 0,
            "audit_manifest_total": 1,
            "audit_coverage_pct": 100.0,
            "final_recommendation": "reason_record_maturity_ready",
            "exact_next_action": "preserve_reason_record_maturity_visibility",
        },
        "durable_artifacts": [
            {
                "artifact_path": "logs/qre_reason_records/latest.jsonl",
                "status": "present",
                "size_bytes": 42,
            }
        ],
        "audit_producer_rows": [],
        "normalization_producer_rows": [],
        "contract_gap_counts": {},
        "linkage_examples_top": [],
    }

    paths = maturity.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_reason_record_maturity/latest.json"
    assert paths["doc"] == "docs/governance/qre_reason_record_maturity.md"
    assert "QRE Reason Record Maturity" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")


def test_module_avoids_static_research_imports() -> None:
    src = Path(maturity.__file__).read_text(encoding="utf-8")
    assert "from research import" not in src
    assert "import research" not in src
