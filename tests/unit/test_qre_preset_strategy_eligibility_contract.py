from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reporting import qre_preset_strategy_eligibility_contract as eligibility


@dataclass(frozen=True)
class PresetFixture:
    name: str
    hypothesis_id: str | None = "trend_pullback_v1"
    enabled: bool = True
    diagnostic_only: bool = False
    excluded_from_candidate_promotion: bool = False
    timeframe: str = "1h"
    universe: tuple[str, ...] = ("BTC-EUR", "ETH-EUR")
    bundle: tuple[str, ...] = ("trend_pullback_v1",)


def _preset(**overrides) -> PresetFixture:
    return PresetFixture(**overrides)


def _request(**overrides) -> dict:
    base = {
        "preset_name": "trend_pullback_crypto_1h",
        "executable_hypothesis_id": "trend_pullback_v1",
        "timeframe": "1h",
        "asset": "BTC-EUR",
        "strategy_template_id": "trend_pullback_v1",
    }
    base.update(overrides)
    return base


def test_exact_request_is_eligible() -> None:
    result = eligibility.validate_request(
        _request(),
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )

    assert result["safe_to_request"] is True
    assert result["eligibility_status"] == "eligible"
    assert result["reason_codes"] == []
    assert result["matched_preset"]["preset_name"] == "trend_pullback_crypto_1h"


def test_missing_preset_name_fails_closed() -> None:
    result = eligibility.validate_request(_request(preset_name=""), presets=[])

    assert result["safe_to_request"] is False
    assert result["eligibility_status"] == "missing_preset_name"


def test_unknown_preset_fails_closed_without_similarity_matching() -> None:
    result = eligibility.validate_request(
        _request(preset_name="trend_pullback_crypto"),
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )

    assert result["safe_to_request"] is False
    assert result["eligibility_status"] == "preset_not_found"


def test_duplicate_preset_names_are_ambiguous_and_unsafe() -> None:
    result = eligibility.validate_request(
        _request(),
        presets=[
            _preset(name="trend_pullback_crypto_1h"),
            _preset(name="trend_pullback_crypto_1h"),
        ],
    )

    assert result["safe_to_request"] is False
    assert result["eligibility_status"] == "ambiguous_request"


def test_disabled_preset_fails_closed() -> None:
    result = eligibility.validate_request(
        _request(),
        presets=[_preset(name="trend_pullback_crypto_1h", enabled=False)],
    )

    assert result["eligibility_status"] == "preset_disabled"


def test_diagnostic_only_preset_requires_explicit_allowance() -> None:
    preset = _preset(name="trend_pullback_crypto_1h", diagnostic_only=True)

    blocked = eligibility.validate_request(_request(), presets=[preset])
    allowed = eligibility.validate_request(
        _request(),
        presets=[preset],
        allow_diagnostic_only=True,
    )

    assert blocked["eligibility_status"] == "preset_diagnostic_only"
    assert blocked["safe_to_request"] is False
    assert allowed["eligibility_status"] == "eligible"


def test_promotion_request_blocks_excluded_preset() -> None:
    result = eligibility.validate_request(
        _request(promotion_path_requested=True),
        presets=[
            _preset(
                name="trend_pullback_crypto_1h",
                excluded_from_candidate_promotion=True,
            )
        ],
    )

    assert result["eligibility_status"] == "preset_excluded_from_promotion"


def test_executable_hypothesis_id_mismatch_fails_closed() -> None:
    result = eligibility.validate_request(
        _request(executable_hypothesis_id="volatility_compression_breakout_v0"),
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )

    assert result["eligibility_status"] == "executable_hypothesis_id_mismatch"


def test_timeframe_asset_and_strategy_mismatches_fail_closed() -> None:
    timeframe = eligibility.validate_request(
        _request(timeframe="4h"),
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )
    asset = eligibility.validate_request(
        _request(asset="SOL-EUR"),
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )
    strategy = eligibility.validate_request(
        _request(strategy_template_id="breakout_momentum"),
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )

    assert timeframe["eligibility_status"] == "timeframe_mismatch"
    assert asset["eligibility_status"] == "asset_not_in_universe"
    assert strategy["eligibility_status"] == "strategy_template_not_in_bundle"


def test_optional_fields_are_checked_only_when_present() -> None:
    request = {"preset_name": "trend_pullback_crypto_1h"}

    result = eligibility.validate_request(
        request,
        presets=[_preset(name="trend_pullback_crypto_1h")],
    )

    assert result["safe_to_request"] is True
    assert result["eligibility_status"] == "eligible"


def test_malformed_request_fails_closed() -> None:
    result = eligibility.validate_request("not-a-row", presets=[])

    assert result["safe_to_request"] is False
    assert result["eligibility_status"] == "malformed_request"


def test_output_is_bounded_and_summary_counts_are_closed() -> None:
    long_name = "preset-" + ("x" * 240)
    result = eligibility.validate_request(
        _request(preset_name=long_name),
        presets=[_preset(name=long_name)],
    )
    summary = eligibility.summarize_eligibility([result])

    assert len(result["request"]["preset_name"]) <= 160
    assert set(summary) == set(eligibility.ELIGIBILITY_STATUSES)
    assert summary["eligible"] == 1


def test_source_has_no_forbidden_calls_or_matching_heuristics() -> None:
    src = Path(eligibility.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "os.system",
        "os.popen",
        "shell=True",
        "research.run_research",
        "SequenceMatcher",
        "difflib",
        "levenshtein",
        "fuzzy",
        "strategy_matrix.csv",
        "research/research_latest.json",
        "seed.jsonl",
        "generated_seed.jsonl",
        "campaigns/",
        "paper/",
        "shadow/",
        "live/",
    )
    for token in forbidden:
        assert token not in src, token
