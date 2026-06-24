from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research.presets import get_preset
from research.qre_failure_to_action_mapper import map_failure_to_action

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "campaign_evidence_decision"

CAMPAIGN_EVIDENCE_PATH: Final[Path] = Path(
    "research/campaign_level_evidence_latest.v1.json"
)
CAMPAIGN_REGISTRY_PATH: Final[Path] = Path(
    "research/campaign_registry_latest.v1.json"
)
MULTIWINDOW_RUN_PATH: Final[Path] = Path(
    "logs/qre_preregistered_multiwindow_evidence_run/latest.json"
)
MULTIWINDOW_CLOSURE_PATH: Final[Path] = Path(
    "logs/qre_multiwindow_evidence_closure/latest.json"
)

DEFAULT_JSON_OUTPUT_PATH: Final[Path] = Path(
    "research/campaign_evidence_decision_latest.v1.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH: Final[Path] = Path(
    "research/campaign_evidence_decision_latest.md"
)

ALLOWED_OUTPUT_PATHS: Final[tuple[str, ...]] = (
    DEFAULT_JSON_OUTPUT_PATH.as_posix(),
    DEFAULT_MARKDOWN_OUTPUT_PATH.as_posix(),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _preset_timeframe(preset_name: str) -> str:
    try:
        preset = get_preset(preset_name)
    except KeyError:
        return ""

    return _text(preset.timeframe)


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _read_json(path: Path) -> tuple[str, dict[str, Any] | None]:
    if not path.is_file():
        return "missing", None

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "malformed", None

    if not isinstance(payload, dict):
        return "malformed", None

    return "present", payload


def _values_for_keys(
    payload: Any,
    wanted_keys: set[str],
) -> dict[str, list[Any]]:
    found = {key: [] for key in wanted_keys}

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in found:
                    found[key].append(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return found


def _string_values(
    found: Mapping[str, Sequence[Any]],
    keys: Sequence[str],
) -> set[str]:
    return {
        _text(value)
        for key in keys
        for value in found.get(key, [])
        if _text(value)
    }


def _exact_collection_match(
    values: Sequence[Any],
    expected: Sequence[Any],
) -> bool:
    expected_values = {_text(value) for value in expected if _text(value)}
    if not expected_values:
        return False

    for value in values:
        if not isinstance(value, list):
            continue
        actual_values = {_text(item) for item in value if _text(item)}
        if actual_values == expected_values:
            return True

    return False


def _campaign_scope(
    campaign_evidence: Mapping[str, Any],
    campaign_registry: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_campaign = campaign_evidence.get("campaign")
    evidence_campaign = (
        dict(evidence_campaign)
        if isinstance(evidence_campaign, Mapping)
        else {}
    )

    campaign_id = _text(evidence_campaign.get("campaign_id"))
    campaigns = campaign_registry.get("campaigns")
    registry_record: Mapping[str, Any] = {}

    if isinstance(campaigns, Mapping):
        candidate = campaigns.get(campaign_id)
        if isinstance(candidate, Mapping):
            registry_record = candidate

    universe = registry_record.get("universe")
    normalized_universe = (
        sorted(_unique_in_order(universe))
        if isinstance(universe, list)
        else []
    )

    preset_name = (
        _text(registry_record.get("preset_name"))
        or _text(evidence_campaign.get("preset_name"))
    )
    timeframe = (
        _text(registry_record.get("timeframe"))
        or _preset_timeframe(preset_name)
    )

    return {
        "campaign_id": campaign_id,
        "hypothesis_id": _text(registry_record.get("hypothesis_id")),
        "preset_name": preset_name,
        "timeframe": timeframe,
        "template_id": _text(registry_record.get("template_id")),
        "strategy_family": (
            _text(registry_record.get("strategy_family"))
            or _text(evidence_campaign.get("strategy_family"))
        ),
        "asset_class": (
            _text(registry_record.get("asset_class"))
            or _text(evidence_campaign.get("asset_class"))
        ),
        "universe": normalized_universe,
        "lineage_root_campaign_id": _text(
            registry_record.get("lineage_root_campaign_id")
        ),
        "parent_campaign_id": _text(
            registry_record.get("parent_campaign_id")
        ),
        "registry_record_present": bool(registry_record),
    }


def _scope_match(
    *,
    target_scope: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> tuple[bool, dict[str, Any]]:
    keys = {
        "campaign_id",
        "campaign_ref",
        "parent_campaign_id",
        "lineage_root_campaign_id",
        "hypothesis_id",
        "hypothesis_ref",
        "preset_id",
        "preset_name",
        "template_id",
        "timeframe",
        "symbols",
        "universe",
        "sampling_plan_id",
        "sampling_plan_ref",
    }
    found = _values_for_keys(artifact, keys)

    campaign_values = _string_values(
        found,
        (
            "campaign_id",
            "campaign_ref",
            "parent_campaign_id",
            "lineage_root_campaign_id",
        ),
    )
    hypothesis_values = _string_values(
        found,
        ("hypothesis_id", "hypothesis_ref"),
    )
    preset_values = _string_values(
        found,
        ("preset_id", "preset_name"),
    )
    template_values = _string_values(found, ("template_id",))
    timeframe_values = _string_values(found, ("timeframe",))

    target_campaign_id = _text(target_scope.get("campaign_id"))
    target_hypothesis_id = _text(target_scope.get("hypothesis_id"))
    target_preset_name = _text(target_scope.get("preset_name"))
    target_template_id = _text(target_scope.get("template_id"))
    target_universe = list(target_scope.get("universe") or [])

    exact_campaign_match = bool(
        target_campaign_id and target_campaign_id in campaign_values
    )
    exact_hypothesis_match = bool(
        target_hypothesis_id
        and target_hypothesis_id in hypothesis_values
    )
    exact_preset_match = bool(
        target_preset_name and target_preset_name in preset_values
    )
    exact_template_match = bool(
        target_template_id and target_template_id in template_values
    )
    exact_universe_match = _exact_collection_match(
        [
            *found.get("symbols", []),
            *found.get("universe", []),
        ],
        target_universe,
    )

    identity_match = exact_template_match or exact_universe_match

    compound_scope_match = bool(
        exact_hypothesis_match
        and exact_preset_match
        and identity_match
    )
    authoritative_scope_match = (
        exact_campaign_match or compound_scope_match
    )

    diagnostics = {
        "authoritative_scope_match": authoritative_scope_match,
        "exact_campaign_match": exact_campaign_match,
        "exact_hypothesis_match": exact_hypothesis_match,
        "exact_preset_match": exact_preset_match,
        "exact_template_match": exact_template_match,
        "exact_universe_match": exact_universe_match,
        "discovered_campaign_ids": sorted(campaign_values),
        "discovered_hypothesis_ids": sorted(hypothesis_values),
        "discovered_preset_ids": sorted(preset_values),
        "discovered_template_ids": sorted(template_values),
        "discovered_timeframes": sorted(timeframe_values),
        "discovered_sampling_plan_ids": sorted(
            _string_values(
                found,
                ("sampling_plan_id", "sampling_plan_ref"),
            )
        ),
    }
    return authoritative_scope_match, diagnostics


def _closure_failure_class(
    closure: Mapping[str, Any],
) -> str | None:
    campaign_outcome = _text(closure.get("campaign_outcome"))
    closure_status = _text(closure.get("closure_status"))

    reason_codes: list[str] = []
    reason_records = closure.get("reason_records")
    if isinstance(reason_records, list):
        for record in reason_records:
            if not isinstance(record, Mapping):
                continue
            codes = record.get("reason_codes")
            if isinstance(codes, list):
                reason_codes.extend(_text(code) for code in codes)

    if (
        campaign_outcome == "all_windows_non_positive_trade_count"
        or closure_status == "all_windows_no_oos_trades"
        or "all_windows_non_positive_trade_count" in reason_codes
    ):
        return "all_preregistered_windows_failed"

    if "insufficient_trades_across_windows" in reason_codes:
        return "insufficient_trades_across_windows"

    return None


def _remaining_window_count(run: Mapping[str, Any]) -> int:
    direct = run.get("remaining_preregistered_window_count")
    if isinstance(direct, int) and direct > 0:
        return direct

    window_results = run.get("window_results")
    if not isinstance(window_results, list):
        return 0

    for row in window_results:
        if not isinstance(row, Mapping):
            continue
        action = row.get("recommended_next_action")
        if not isinstance(action, Mapping):
            continue
        if (
            _text(action.get("recommended_action"))
            == "run_next_preregistered_window"
        ):
            return 1

    return 0


def _remaining_regime_count(run: Mapping[str, Any]) -> int:
    direct = run.get("remaining_preregistered_regime_count")
    if isinstance(direct, int) and direct > 0:
        return direct

    window_results = run.get("window_results")
    if not isinstance(window_results, list):
        return 0

    for row in window_results:
        if not isinstance(row, Mapping):
            continue
        action = row.get("recommended_next_action")
        if not isinstance(action, Mapping):
            continue
        if (
            _text(action.get("recommended_action"))
            == "run_next_preregistered_regime"
        ):
            return 1

    return 0


def _ignored_artifact(
    *,
    path: Path,
    status: str,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "artifact_path": path.as_posix(),
        "status": status,
        "reason": (
            "scope_mismatch"
            if status == "present"
            else f"artifact_{status}"
        ),
    }
    if diagnostics:
        row.update(
            {
                "discovered_campaign_ids": list(
                    diagnostics.get("discovered_campaign_ids", [])
                ),
                "discovered_hypothesis_ids": list(
                    diagnostics.get("discovered_hypothesis_ids", [])
                ),
                "discovered_preset_ids": list(
                    diagnostics.get("discovered_preset_ids", [])
                ),
                "discovered_sampling_plan_ids": list(
                    diagnostics.get(
                        "discovered_sampling_plan_ids",
                        [],
                    )
                ),
            }
        )
    return row


def build_campaign_evidence_decision(
    *,
    campaign_evidence: Mapping[str, Any] | None,
    campaign_registry: Mapping[str, Any] | None,
    multiwindow_run: Mapping[str, Any] | None,
    multiwindow_closure: Mapping[str, Any] | None,
    run_status: str = "missing",
    closure_status: str = "missing",
) -> dict[str, Any]:
    evidence = (
        campaign_evidence
        if isinstance(campaign_evidence, Mapping)
        else {}
    )
    registry = (
        campaign_registry
        if isinstance(campaign_registry, Mapping)
        else {}
    )

    scope = _campaign_scope(evidence, registry)

    failure_attribution = evidence.get("failure_attribution")
    failure_attribution = (
        failure_attribution
        if isinstance(failure_attribution, Mapping)
        else {}
    )

    screening_evidence = evidence.get("screening_evidence")
    screening_evidence = (
        screening_evidence
        if isinstance(screening_evidence, Mapping)
        else {}
    )

    interpretation = evidence.get("interpretation")
    interpretation = (
        interpretation
        if isinstance(interpretation, Mapping)
        else {}
    )

    attributed = failure_attribution.get("attributed") is True
    owner_verified = screening_evidence.get("owner_verified") is True
    primary_limitation = _text(
        interpretation.get("primary_limitation")
    )

    ignored_artifacts: list[dict[str, Any]] = []
    evidence_refs = [
        CAMPAIGN_EVIDENCE_PATH.as_posix(),
        CAMPAIGN_REGISTRY_PATH.as_posix(),
    ]

    if (
        not scope.get("campaign_id")
        or not scope.get("registry_record_present")
        or not attributed
        or not owner_verified
    ):
        mapped = map_failure_to_action(
            failure_class="unknown_campaign_evidence_state"
        )
        decision_status = "incomplete_unattributed"
        scope_match_status = "campaign_scope_unverified"
        selected_source = "campaign_level_evidence"
    else:
        matching_closure = False
        closure_diagnostics: dict[str, Any] | None = None

        if closure_status == "present" and isinstance(
            multiwindow_closure,
            Mapping,
        ):
            matching_closure, closure_diagnostics = _scope_match(
                target_scope=scope,
                artifact=multiwindow_closure,
            )
            if not matching_closure:
                ignored_artifacts.append(
                    _ignored_artifact(
                        path=MULTIWINDOW_CLOSURE_PATH,
                        status=closure_status,
                        diagnostics=closure_diagnostics,
                    )
                )
        elif closure_status == "malformed":
            ignored_artifacts.append(
                _ignored_artifact(
                    path=MULTIWINDOW_CLOSURE_PATH,
                    status=closure_status,
                )
            )

        matching_run = False
        run_diagnostics: dict[str, Any] | None = None

        if run_status == "present" and isinstance(
            multiwindow_run,
            Mapping,
        ):
            matching_run, run_diagnostics = _scope_match(
                target_scope=scope,
                artifact=multiwindow_run,
            )
            if not matching_run:
                ignored_artifacts.append(
                    _ignored_artifact(
                        path=MULTIWINDOW_RUN_PATH,
                        status=run_status,
                        diagnostics=run_diagnostics,
                    )
                )
        elif run_status == "malformed":
            ignored_artifacts.append(
                _ignored_artifact(
                    path=MULTIWINDOW_RUN_PATH,
                    status=run_status,
                )
            )

        closure_failure = (
            _closure_failure_class(multiwindow_closure)
            if matching_closure
            and isinstance(multiwindow_closure, Mapping)
            else None
        )

        if closure_failure:
            mapped = map_failure_to_action(
                failure_class=closure_failure
            )
            decision_status = "decision_ready"
            scope_match_status = "matching_multiwindow_closure"
            selected_source = MULTIWINDOW_CLOSURE_PATH.as_posix()
            evidence_refs.append(
                MULTIWINDOW_CLOSURE_PATH.as_posix()
            )
        elif matching_run and isinstance(multiwindow_run, Mapping):
            remaining_windows = _remaining_window_count(
                multiwindow_run
            )
            remaining_regimes = _remaining_regime_count(
                multiwindow_run
            )
            mapped = map_failure_to_action(
                failure_class="non_positive_oos_trade_count",
                remaining_preregistered_window_count=remaining_windows,
                remaining_preregistered_regime_count=remaining_regimes,
            )
            decision_status = "decision_ready"
            scope_match_status = "matching_multiwindow_run"
            selected_source = MULTIWINDOW_RUN_PATH.as_posix()
            evidence_refs.append(MULTIWINDOW_RUN_PATH.as_posix())
        elif primary_limitation == "insufficient_trades":
            mapped = map_failure_to_action(
                failure_class="insufficient_window_length"
            )
            decision_status = "decision_ready"
            scope_match_status = (
                "no_matching_preregistered_evidence"
            )
            selected_source = CAMPAIGN_EVIDENCE_PATH.as_posix()
        else:
            mapped = map_failure_to_action(
                failure_class="unknown_campaign_evidence_state"
            )
            decision_status = "incomplete_unattributed"
            scope_match_status = "unsupported_failure_attribution"
            selected_source = CAMPAIGN_EVIDENCE_PATH.as_posix()

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "decision_status": decision_status,
        "scope_match_status": scope_match_status,
        "campaign_scope": scope,
        "source_failure_attribution": {
            "attributed": attributed,
            "owner_verified": owner_verified,
            "primary_limitation": primary_limitation,
            "evidence_status": _text(
                evidence.get("evidence_status")
            ),
        },
        "failure_class": mapped.get("failure_class", ""),
        "recommended_action": mapped.get(
            "recommended_action",
            "",
        ),
        "action_authority": mapped.get(
            "action_authority",
            "",
        ),
        "reason_codes": list(mapped.get("reason_codes", [])),
        "prerequisites": list(mapped.get("prerequisites", [])),
        "selected_source": selected_source,
        "evidence_refs": _unique_in_order(evidence_refs),
        "ignored_artifacts": ignored_artifacts,
        "artifact_inputs": {
            "campaign_level_evidence": {
                "path": CAMPAIGN_EVIDENCE_PATH.as_posix(),
                "status": (
                    "present"
                    if campaign_evidence is not None
                    else "missing"
                ),
            },
            "campaign_registry": {
                "path": CAMPAIGN_REGISTRY_PATH.as_posix(),
                "status": (
                    "present"
                    if campaign_registry is not None
                    else "missing"
                ),
            },
            "multiwindow_run": {
                "path": MULTIWINDOW_RUN_PATH.as_posix(),
                "status": run_status,
            },
            "multiwindow_closure": {
                "path": MULTIWINDOW_CLOSURE_PATH.as_posix(),
                "status": closure_status,
            },
        },
        "safety_invariants": {
            "can_execute": False,
            "can_spawn_campaigns": False,
            "can_mutate_queue": False,
            "can_change_policy": False,
            "can_change_presets": False,
            "can_change_strategy": False,
            "can_access_paper_shadow_live": False,
        },
    }


def build_from_current_artifacts(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    evidence_status, campaign_evidence = _read_json(
        repo_root / CAMPAIGN_EVIDENCE_PATH
    )
    registry_status, campaign_registry = _read_json(
        repo_root / CAMPAIGN_REGISTRY_PATH
    )
    run_status, multiwindow_run = _read_json(
        repo_root / MULTIWINDOW_RUN_PATH
    )
    closure_status, multiwindow_closure = _read_json(
        repo_root / MULTIWINDOW_CLOSURE_PATH
    )

    report = build_campaign_evidence_decision(
        campaign_evidence=campaign_evidence,
        campaign_registry=campaign_registry,
        multiwindow_run=multiwindow_run,
        multiwindow_closure=multiwindow_closure,
        run_status=run_status,
        closure_status=closure_status,
    )

    report["artifact_inputs"]["campaign_level_evidence"][
        "status"
    ] = evidence_status
    report["artifact_inputs"]["campaign_registry"][
        "status"
    ] = registry_status
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    scope = report.get("campaign_scope")
    scope = scope if isinstance(scope, Mapping) else {}

    lines = [
        "# Campaign Evidence Decision",
        "",
        f"- decision_status: {report.get('decision_status', '')}",
        f"- scope_match_status: {report.get('scope_match_status', '')}",
        f"- campaign_id: {scope.get('campaign_id', '')}",
        f"- hypothesis_id: {scope.get('hypothesis_id', '')}",
        f"- preset_name: {scope.get('preset_name', '')}",
        f"- failure_class: {report.get('failure_class', '')}",
        f"- recommended_action: {report.get('recommended_action', '')}",
        f"- action_authority: {report.get('action_authority', '')}",
        f"- can_execute: {bool((report.get('safety_invariants') or {}).get('can_execute', False))}",
        "",
        "## Ignored artifacts",
    ]

    ignored = report.get("ignored_artifacts")
    if isinstance(ignored, list) and ignored:
        for row in ignored:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                f"- {row.get('artifact_path', '')}: "
                f"{row.get('reason', '')}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if normalized not in ALLOWED_OUTPUT_PATHS:
        raise ValueError(f"output_path_not_allowlisted:{normalized}")


def _atomic_write_text(path: Path, content: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    json_path = repo_root / DEFAULT_JSON_OUTPUT_PATH
    markdown_path = repo_root / DEFAULT_MARKDOWN_OUTPUT_PATH

    _atomic_write_text(
        DEFAULT_JSON_OUTPUT_PATH,
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n",
    )
    _atomic_write_text(
        DEFAULT_MARKDOWN_OUTPUT_PATH,
        render_markdown(report),
    )

    return {
        "json": json_path.as_posix(),
        "markdown": markdown_path.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.campaign_evidence_decision",
        description=(
            "Build a read-only, scope-aware campaign evidence decision."
        ),
    )
    parser.add_argument(
        "--from-current-artifacts",
        action="store_true",
        required=True,
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
    )
    args = parser.parse_args(argv)

    report = build_from_current_artifacts()

    if not args.no_write:
        report["_artifact_paths"] = write_outputs(report)

    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
