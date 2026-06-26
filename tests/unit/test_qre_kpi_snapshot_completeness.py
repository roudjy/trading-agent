from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_kpi_snapshot_completeness as report


def _row(rows: list[dict[str, object]], kpi_family: str, kpi_id: str) -> dict[str, object]:
    for row in rows:
        if row["kpi_family"] == kpi_family and row["kpi_id"] == kpi_id:
            return row
    raise AssertionError(f"missing row: {kpi_family}/{kpi_id}")


def test_collect_snapshot_surfaces_numeric_and_explicit_unavailable_states() -> None:
    snapshot = report.collect_snapshot(
        repo_root=Path("."),
        max_candidates=15,
        frozen_utc="2026-06-26T00:10:00Z",
    )

    assert snapshot["report_kind"] == "qre_kpi_snapshot_completeness"
    assert snapshot["summary"]["all_kpis_numeric_or_explicit_unavailable"] is True
    assert snapshot["summary"]["numeric_value_count"] > 0
    assert snapshot["summary"]["explicit_unavailable_count"] > 0

    rows = snapshot["kpi_rows"]
    basket = _row(rows, "trusted_loop_operational", "basket_inventory_count")
    assert basket["status"] == "numeric"
    assert basket["value"] == 15

    oab = _row(rows, "research_quality", "OAB")
    assert oab["status"] == "explicit_unavailable"
    assert int(oab["partial_evidence_count"]) >= 0


def test_collect_snapshot_is_deterministic_with_frozen_timestamp() -> None:
    a = report.collect_snapshot(
        repo_root=Path("."),
        max_candidates=15,
        frozen_utc="2026-06-26T00:10:00Z",
    )
    b = report.collect_snapshot(
        repo_root=Path("."),
        max_candidates=15,
        frozen_utc="2026-06-26T00:10:00Z",
    )

    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["snapshot_identity"]["snapshot_id"] == b["snapshot_identity"]["snapshot_id"]


def test_write_outputs_writes_latest_timestamp_history_and_markdown(tmp_path: Path) -> None:
    snapshot = report.collect_snapshot(
        repo_root=Path("."),
        max_candidates=15,
        frozen_utc="2026-06-26T00:10:00Z",
    )

    output_dir = tmp_path / "logs" / "qre_kpi_snapshot_completeness"
    paths = report.write_outputs(snapshot, output_dir=output_dir, repo_root=tmp_path)

    assert paths["latest"].endswith("logs/qre_kpi_snapshot_completeness/latest.json")
    assert paths["timestamped"].endswith("2026-06-26T00-10-00Z.json")
    assert paths["history"].endswith("logs/qre_kpi_snapshot_completeness/history.jsonl")
    assert paths["operator_summary"].endswith(
        "logs/qre_kpi_snapshot_completeness/operator_summary.md"
    )
    assert (output_dir / "latest.json").is_file()
    assert (output_dir / "history.jsonl").is_file()
    assert "# QRE KPI Snapshot Completeness" in (
        output_dir / "operator_summary.md"
    ).read_text(encoding="utf-8")


def test_write_outputs_refuses_writes_outside_allowlist(tmp_path: Path) -> None:
    snapshot = report.collect_snapshot(
        repo_root=Path("."),
        max_candidates=15,
        frozen_utc="2026-06-26T00:10:00Z",
    )

    try:
        report.write_outputs(snapshot, output_dir=tmp_path / "elsewhere", repo_root=tmp_path)
    except ValueError as exc:
        assert "refusing write outside allowlist" in str(exc)
    else:
        raise AssertionError("expected allowlist failure")
