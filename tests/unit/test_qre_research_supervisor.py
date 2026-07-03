from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_research_supervisor as supervisor


def test_supervisor_no_change_skip(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    monkeypatch.setattr(supervisor, "REPO_ROOT", repo_root)
    monkeypatch.setattr(supervisor, "LEASE_PATH", repo_root / "logs/qre_research_supervisor/lease.json")
    monkeypatch.setattr(supervisor, "STATUS_PATH", repo_root / "logs/qre_research_supervisor/latest.json")
    monkeypatch.setattr(supervisor, "HEALTHCHECK_PATH", repo_root / "logs/qre_research_supervisor/healthcheck.json")
    monkeypatch.setattr(supervisor, "SOURCE_QUALIFICATIONS_PATH", repo_root / "generated_research/alpha_discovery/source_qualifications/latest.json")

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
