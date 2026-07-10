from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools import qre_architecture_impact_report as impact


def test_empty_report_is_safe() -> None:
    report = impact.build_report(())

    assert report["verdict"] == "safe"
    assert report["changed_qre_files"] == []
    assert report["operator_decision_required"] == []
    assert report["safety"]["read_only"] is True
    assert report["safety"]["runtime_behavior_changed"] is False


def test_registry_change_requires_review() -> None:
    report = impact.build_report(("docs/architecture/qre_architecture_registry.v1.json",))

    assert report["verdict"] == "review_required"
    assert "docs/architecture/qre_architecture_registry.v1.json" in report["changed_qre_files"]


def test_new_qre_python_module_requires_registry_review(tmp_path: Path) -> None:
    module = tmp_path / "packages" / "qre_research" / "new_parallel_loop.py"
    module.parent.mkdir(parents=True)
    module.write_text("from packages.qre_research.canonical_contracts import CandidateSpec\n", encoding="utf-8")

    report = impact.build_report(("packages/qre_research/new_parallel_loop.py",), repo_root=tmp_path)

    assert report["verdict"] == "review_required"
    assert report["new_producer_modules"] == ["packages/qre_research/new_parallel_loop.py"]
    assert report["new_consumer_modules"] == ["packages/qre_research/new_parallel_loop.py"]
    assert "new_producer_modules" in report["operator_decision_required"]


def test_protected_output_touch_is_blocked() -> None:
    report = impact.build_report(("research/research_latest.json",))

    assert report["verdict"] == "blocked"
    assert report["protected_outputs_touched"] == ["research/research_latest.json"]
    assert "protected_outputs" in report["operator_decision_required"]


def test_blocked_authority_touch_is_blocked(tmp_path: Path) -> None:
    path = tmp_path / "packages" / "qre_research" / "review.py"
    path.parent.mkdir(parents=True)
    path.write_text("shadow_authority = True\n", encoding="utf-8")

    report = impact.build_report(("packages/qre_research/review.py",), repo_root=tmp_path)

    assert report["verdict"] == "blocked"
    assert "shadow_authority" in report["authority_flags_touched"]
    assert "blocked_authority_flags" in report["operator_decision_required"]


def test_cli_json_output_is_parseable() -> None:
    assert impact.main(["--json"]) == 0


def test_git_changed_path_collection_filters_qre_paths(tmp_path: Path) -> None:
    subprocess.run(("git", "init"), cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.name", "Test User"), cwd=tmp_path, check=True)
    tracked = tmp_path / "README.md"
    tracked.write_text("baseline\n", encoding="utf-8")
    subprocess.run(("git", "add", "README.md"), cwd=tmp_path, check=True)
    subprocess.run(("git", "commit", "-m", "baseline"), cwd=tmp_path, check=True, capture_output=True)

    qre_path = tmp_path / "tools" / "qre_new_report.py"
    ignored_path = tmp_path / "tmp" / "qre_ignored.py"
    qre_path.parent.mkdir()
    ignored_path.parent.mkdir()
    qre_path.write_text("VALUE = 1\n", encoding="utf-8")
    ignored_path.write_text("VALUE = 2\n", encoding="utf-8")

    paths = impact.changed_paths_from_git(repo_root=tmp_path)

    assert paths == ("tools/qre_new_report.py",)


def test_json_encoder_is_stable() -> None:
    report = impact.build_report(("research/research_latest.json",))

    encoded = json.loads(impact._json(report))

    assert encoded["verdict"] == "blocked"
