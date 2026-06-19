from __future__ import annotations

from pathlib import Path

from research.qre_source_identity_authority_normalization import (
    build_source_identity_authority_normalization,
    write_outputs,
)


def _breadth_report() -> dict[str, object]:
    return {
        "report_kind": "qre_evidence_breadth_framework",
        "coverage_matrix": [
            {
                "dimension": "basket",
                "scope_key": "seed::trend_continuation_daily_v1::ASML",
                "symbol": "ASML",
                "region": "NL/EU",
                "behavior_id": "trend_continuation",
                "timeframe": "1d",
            },
            {
                "dimension": "basket",
                "scope_key": "seed::relative_strength_vs_sector_daily_v1::ASMI",
                "symbol": "ASMI",
                "region": "NL/EU",
                "behavior_id": "relative_strength_vs_sector",
                "timeframe": "1d",
            },
        ],
    }


def _source_quality_report(*, ready: bool = True) -> dict[str, object]:
    return {
        "report_kind": "qre_data_source_quality_readiness",
        "summary": {
            "status": "ready" if ready else "not_ready",
            "research_ready": ready,
        },
    }


def _discovery_identity_report() -> dict[str, object]:
    return {
        "report_kind": "qre_discovery_source_identity_diagnostics",
        "rows": [
            {
                "instrument_symbol": "ASML",
                "canonical_symbol": "ASML",
                "selected_provider_symbol": "ASML.AS",
                "candidate_aliases": ["ASML.AS"],
                "provider_symbol_status": "verified",
                "is_provider_symbol_verified": True,
            },
            {
                "instrument_symbol": "ASMI",
                "canonical_symbol": "ASMI",
                "selected_provider_symbol": "",
                "candidate_aliases": ["ASMI.AS", "ASMI.AS2"],
                "provider_symbol_status": "candidate_alias_requires_verification",
                "is_provider_symbol_verified": False,
            },
        ],
    }


def _instrument_identity_report() -> dict[str, object]:
    return {
        "report_kind": "instrument_identity",
        "rows": [
            {
                "symbol": "ASML",
                "canonical_id": "eq.asml.nl",
                "provider_symbol": "ASML.AS",
                "candidate_provider_symbols": ["ASML.AS"],
                "identity_status": "OK",
                "eligible_for_hypothesis_seed": True,
            },
            {
                "symbol": "ASMI",
                "canonical_id": "eq.asmi.nl",
                "provider_symbol": "",
                "candidate_provider_symbols": ["ASMI.AS", "ASMI.AS2"],
                "identity_status": "WARN",
                "eligible_for_hypothesis_seed": False,
            },
        ],
    }


def test_source_identity_authority_normalization_is_deterministic_and_fail_closed() -> None:
    left = build_source_identity_authority_normalization(
        breadth_report=_breadth_report(),
        source_quality_report=_source_quality_report(),
        discovery_identity_report=_discovery_identity_report(),
        instrument_identity_report=_instrument_identity_report(),
    )
    right = build_source_identity_authority_normalization(
        breadth_report=_breadth_report(),
        source_quality_report=_source_quality_report(),
        discovery_identity_report=_discovery_identity_report(),
        instrument_identity_report=_instrument_identity_report(),
    )

    assert left == right
    rows = {row["symbol"]: row for row in left["rows"]}
    assert rows["ASML"]["authority_status"] == "normalized_context_ready"
    assert rows["ASMI"]["authority_status"] == "blocked_provider_symbol_ambiguity"
    assert "candidate_alias_requires_verification" in rows["ASMI"]["authority_reasons"]
    assert left["summary"]["blocked_scope_count"] == 1


def test_source_identity_authority_normalization_blocks_when_source_quality_not_ready() -> None:
    report = build_source_identity_authority_normalization(
        breadth_report=_breadth_report(),
        source_quality_report=_source_quality_report(ready=False),
        discovery_identity_report=_discovery_identity_report(),
        instrument_identity_report=_instrument_identity_report(),
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["ASML"]["authority_status"] == "blocked_source_quality_not_ready"
    assert report["summary"]["exact_next_action"] == "stabilize_source_quality_manifest_and_readiness"


def test_source_identity_authority_outputs_use_allowlisted_location(tmp_path: Path) -> None:
    report = build_source_identity_authority_normalization(
        breadth_report=_breadth_report(),
        source_quality_report=_source_quality_report(),
        discovery_identity_report=_discovery_identity_report(),
        instrument_identity_report=_instrument_identity_report(),
    )

    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_source_identity_authority_normalization/latest.json"
    assert (tmp_path / paths["latest"]).is_file()
