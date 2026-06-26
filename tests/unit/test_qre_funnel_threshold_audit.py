from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_funnel_threshold_audit as report


def _criterion(rows: list[dict[str, object]], criterion_id: str) -> dict[str, object]:
    for row in rows:
        if row["criterion_id"] == criterion_id:
            return row
    raise AssertionError(f"missing criterion row: {criterion_id}")


def test_collect_snapshot_surfaces_funnel_counts_and_recommendations() -> None:
    snapshot = report.collect_snapshot(
        repo_root=Path("."),
        frozen_utc="2026-06-26T00:20:00Z",
    )

    assert snapshot["report_kind"] == "qre_funnel_threshold_audit"
    assert snapshot["funnel_counts"]["raw_candidate_count"] == 2
    assert snapshot["funnel_counts"]["screening_pass_count"] == 6
    assert snapshot["funnel_counts"]["screening_reject_count"] == 9
    assert snapshot["funnel_counts"]["oos_accepted_count"] == 1
    assert snapshot["summary"]["all_criteria_have_exactly_one_recommendation"] is True

    sufficient_trades = _criterion(snapshot["criterion_rows"], "sufficient_trades")
    assert sufficient_trades["threshold_value"] == 10.0
    assert sufficient_trades["fail_count"] > 0
    assert sufficient_trades["recommendation"] in {
        "stratify",
        "insufficient_evidence_to_change",
    }

    drawdown = _criterion(snapshot["criterion_rows"], "drawdown_within_limit")
    assert drawdown["threshold_value"] == 0.45
    assert drawdown["recommendation"] == "keep"


def test_collect_snapshot_is_deterministic_with_frozen_timestamp() -> None:
    a = report.collect_snapshot(
        repo_root=Path("."),
        frozen_utc="2026-06-26T00:20:00Z",
    )
    b = report.collect_snapshot(
        repo_root=Path("."),
        frozen_utc="2026-06-26T00:20:00Z",
    )

    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["snapshot_identity"]["snapshot_id"] == b["snapshot_identity"]["snapshot_id"]


def test_write_outputs_writes_latest_history_and_doc(tmp_path: Path) -> None:
    snapshot = report.collect_snapshot(
        repo_root=Path("."),
        frozen_utc="2026-06-26T00:20:00Z",
    )

    output_dir = tmp_path / "logs" / "qre_funnel_threshold_audit"
    doc_path = tmp_path / "docs" / "governance" / "qre_funnel_threshold_audit.md"
    paths = report.write_outputs(
        snapshot,
        output_dir=output_dir,
        doc_path=doc_path,
        repo_root=tmp_path,
    )

    assert paths["latest"].endswith("logs/qre_funnel_threshold_audit/latest.json")
    assert paths["history"].endswith("logs/qre_funnel_threshold_audit/history.jsonl")
    assert paths["doc"].endswith("docs/governance/qre_funnel_threshold_audit.md")
    assert (output_dir / "latest.json").is_file()
    assert (output_dir / "history.jsonl").is_file()
    assert "# QRE Funnel Census and Threshold-Distance Audit" in doc_path.read_text(
        encoding="utf-8"
    )


def test_write_outputs_refuses_writes_outside_allowlist(tmp_path: Path) -> None:
    snapshot = report.collect_snapshot(
        repo_root=Path("."),
        frozen_utc="2026-06-26T00:20:00Z",
    )

    try:
        report.write_outputs(
            snapshot,
            output_dir=tmp_path / "elsewhere",
            doc_path=tmp_path / "docs" / "governance" / "qre_funnel_threshold_audit.md",
            repo_root=tmp_path,
        )
    except ValueError as exc:
        assert "refusing write outside allowlist" in str(exc)
    else:
        raise AssertionError("expected allowlist failure")
