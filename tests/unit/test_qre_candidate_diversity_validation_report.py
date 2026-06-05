from __future__ import annotations

from reporting import qre_candidate_diversity_validation_report as report


def test_candidate_diversity_validation_report_is_operator_readable() -> None:
    snapshot = report.collect_snapshot(
        branch="test/qre-controlled-validation-candidate-diversity-harness",
        commits=[
            {
                "message": "test: add controlled validation candidate diversity harness",
                "sha": "ae266bd",
                "purpose": "fixture + multiple candidate outcomes",
            },
            {
                "message": "feat: add QRE production discovery universe seed",
                "sha": "58920c5",
                "purpose": "read-only multi-region discovery catalog",
            },
            {
                "message": "docs: add operator report for candidate diversity validation",
                "sha": "HEAD",
                "purpose": "operator-facing explanation of scope and limits",
            },
        ],
        tests=[
            "python -m pytest tests/unit/test_qre_controlled_validation_candidate_diversity_harness.py -q",
            "python -m pytest tests/unit/test_qre_production_discovery_catalog.py -q",
        ],
        architecture_tests="python -m pytest tests/architecture -q",
        git_diff_check="clean",
    )

    assert snapshot["next_action"] == "READ_ONLY_REAL_BASKET_DIAGNOSIS"
    assert len(snapshot["tested_rows"]) == 15
    assert len(snapshot["production_seed_rows"]) == 4
    assert snapshot["validation"]["frozen_contracts_untouched"] is True
    assert snapshot["validation"]["protected_execution_paths_untouched"] is True

    markdown = report.render_markdown(snapshot)
    assert "# QRE Candidate Diversity + Production Discovery Seed Report" in markdown
    assert "## 1. Korte conclusie" in markdown
    assert "## 2. Wat is getest" in markdown
    assert "## 3. Production discovery seed" in markdown
    assert "## 6. Wat dit niet bewijst" in markdown
    assert "- dit bewijst geen echte alpha" in markdown
    assert "- dit activeert geen paper/shadow/live" in markdown
    assert "- NEXT_ACTION: READ_ONLY_REAL_BASKET_DIAGNOSIS" in markdown
    assert "test/qre-controlled-validation-candidate-diversity-harness" in markdown
