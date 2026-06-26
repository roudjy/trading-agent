from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final

from packages.qre_research import opportunity_value
from research.strategy_hypothesis_catalog import STRATEGY_HYPOTHESIS_CATALOG


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_opportunity_research_value"
MODULE_VERSION: Final[str] = "ade-qre-017o-2026-06-26"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_opportunity_research_value")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_opportunity_research_value.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_opportunity_research_value/",
    "docs/governance/qre_opportunity_research_value.md",
)
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_EVIDENCE_PATH: Final[Path] = Path("logs/qre_behavior_thesis_evidence/latest.json")
DEFAULT_PRIOR_FAILURE_PATH: Final[Path] = Path("logs/qre_prior_failure_retrieval/latest.json")
DEFAULT_BREADTH_PATH: Final[Path] = Path("logs/qre_evidence_breadth_framework/latest.json")
DEFAULT_SOURCE_AUTHORITY_PATH: Final[Path] = Path(
    "logs/qre_source_identity_authority_normalization/latest.json"
)
DEFAULT_ROUTER_PATH: Final[Path] = Path("logs/qre_research_cycle_router/latest.json")
DEFAULT_DISCOVERY_DIGEST_PATH: Final[Path] = Path("logs/hypothesis_discovery_minimal/latest.json")
DEFAULT_INFORMATION_GAIN_PATH: Final[Path] = Path(
    "research/campaigns/evidence/information_gain_latest.v1.json"
)

NEXT_ACTION_VALUES: Final[tuple[str, ...]] = (
    "advance_to_routing_comparison",
    "increase_evidence_density",
    "resolve_data_readiness",
    "operator_review_context_only",
    "keep_fail_closed",
)
ROW_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "thesis_id",
    "source_hypothesis_id",
    "behavior_family",
    "thesis_status",
    "opportunity_score",
    "priority_band",
    "recommended_next_action",
    "component_scores",
    "component_statuses",
    "provenance_refs",
    "schema_version",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_opportunity_research_value: refusing write outside allowlist: {path!r}"
        )


def _unique(values: list[Any] | tuple[Any, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _sha(value: Any) -> str:
    blob = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _source_catalog_index() -> dict[str, dict[str, Any]]:
    return {
        row.hypothesis_id: {
            "cost_class": row.cost_class,
            "status": row.status,
        }
        for row in STRATEGY_HYPOTHESIS_CATALOG
    }


def _normalize_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _behavior_aliases(row: dict[str, Any]) -> tuple[str, ...]:
    values = [
        _text(row.get("behavior_family")),
        _text(row.get("strategy_family")),
        _text(row.get("source_hypothesis_id")).replace("_v0", "").replace("_v1", ""),
    ]
    return _unique(values)


def _match_breadth_row(
    breadth_rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    aliases = {_normalize_token(value) for value in _behavior_aliases(row)}
    best: dict[str, Any] | None = None
    best_ref = ""
    for index, item in enumerate(breadth_rows):
        if _text(item.get("dimension")) != "behavior":
            continue
        scope_key = _text(item.get("scope_key"))
        normalized = _normalize_token(scope_key)
        if normalized in aliases:
            return (
                dict(item),
                f"{DEFAULT_BREADTH_PATH.as_posix()}#coverage_matrix[{index}]",
            )
        if any(alias and alias in normalized for alias in aliases):
            best = dict(item)
            best_ref = f"{DEFAULT_BREADTH_PATH.as_posix()}#coverage_matrix[{index}]"
    return (best, best_ref)


def _matching_source_authority_rows(
    source_rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    aliases = {_normalize_token(value) for value in _behavior_aliases(row)}
    matches: list[tuple[dict[str, Any], str]] = []
    for index, item in enumerate(source_rows):
        behavior_id = _normalize_token(_text(item.get("behavior_id")))
        scope_key = _normalize_token(_text(item.get("scope_key")))
        if behavior_id in aliases or any(alias and alias in scope_key for alias in aliases):
            matches.append(
                (
                    dict(item),
                    f"{DEFAULT_SOURCE_AUTHORITY_PATH.as_posix()}#rows[{index}]",
                )
            )
    return matches


def _matching_router_row(
    router_rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    aliases = {_normalize_token(value) for value in _behavior_aliases(row)}
    for index, item in enumerate(router_rows):
        behavior_id = _normalize_token(
            _text((item.get("target_hypothesis") or {}).get("behavior_id"))
            or _text((item.get("proposed_scope") or {}).get("behavior_id"))
        )
        if behavior_id and behavior_id in aliases:
            return (
                dict(item),
                f"{DEFAULT_ROUTER_PATH.as_posix()}#eligible_directions[{index}]",
            )
    return (None, "")


def _information_gain_index(payload: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    score = (payload.get("information_gain") or {}).get("score")
    hypothesis_id = _text(payload.get("hypothesis_id"))
    if hypothesis_id and isinstance(score, (int, float)):
        return {hypothesis_id: opportunity_value.bounded_float(score)}
    return {}


def _discovery_index(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return index
    for item in _read_rows(payload, "items"):
        hypothesis_id = _text(item.get("hypothesis_id"))
        if hypothesis_id:
            index[hypothesis_id] = dict(item)
    return index


def _component_from_thesis_status(status: str) -> tuple[float, str]:
    if status == "research_ready":
        return (1.0, "present")
    if status == "draft":
        return (0.45, "derived_proxy")
    if status in {"blocked", "deprecated"}:
        return (0.0, "blocked")
    return (0.0, "missing")


def _component_from_signal_density(value: str) -> tuple[float, str]:
    mapping = {
        "dense": 1.0,
        "moderate": 0.7,
        "sparse": 0.35,
        "unknown": 0.0,
        "blocked": 0.0,
    }
    score = mapping.get(value, 0.0)
    status = "blocked" if value == "blocked" else "present" if value in mapping else "missing"
    return (score, status)


def _component_from_orthogonality(
    *,
    behavior_family: str,
    family_counts: dict[str, int],
) -> tuple[float, str]:
    count = int(family_counts.get(behavior_family, 0) or 0)
    if count <= 1:
        return (1.0, "derived_proxy")
    if count == 2:
        return (0.6, "derived_proxy")
    return (0.3, "derived_proxy")


def _component_from_prior_failure(row: dict[str, Any] | None) -> tuple[float, str]:
    if not isinstance(row, dict):
        return (0.0, "missing")
    summary_status = _text(row.get("summary_status"))
    mapping = {
        "missing_context": 1.0,
        "dead_zone_visible": 0.55,
        "prior_failure_visible": 0.35,
        "prior_failure_dead_zone_visible": 0.20,
        "prior_failure_dead_zone_action_visible": 0.10,
    }
    return (mapping.get(summary_status, 0.0), "present")


def _component_from_null_controls(values: list[Any] | tuple[Any, ...]) -> tuple[float, str]:
    controls = [_text(value) for value in values if _text(value)]
    if not controls:
        return (0.0, "missing")
    if all(control.startswith("blocked:") for control in controls):
        return (0.0, "blocked")
    return (1.0, "present")


def _component_from_regime_coverage(row: dict[str, Any] | None) -> tuple[float, str]:
    if not isinstance(row, dict):
        return (0.0, "missing")
    score = 0.0
    if int(row.get("inventory_count") or 0) > 0:
        score += 0.25
    if int(row.get("regime_count") or 0) > 0:
        score += 0.25
    if int(row.get("independent_window_count") or 0) > 0:
        score += 0.25
    if int(row.get("accepted_oos_count") or 0) > 0:
        score += 0.25
    return (round(score, 6), "present")


def _component_from_historical_evidence(
    evidence_row: dict[str, Any] | None,
    breadth_row: dict[str, Any] | None,
) -> tuple[float, str]:
    if not isinstance(evidence_row, dict):
        return (0.0, "missing")
    score = 0.0
    if int(evidence_row.get("supporting_evidence_count") or 0) > 0:
        score += 0.2
    if isinstance(breadth_row, dict) and int(breadth_row.get("accepted_lineage_count") or 0) > 0:
        score += 0.3
    if isinstance(breadth_row, dict) and int(breadth_row.get("accepted_oos_count") or 0) > 0:
        score += 0.3
    if int(evidence_row.get("contradicting_evidence_count") or 0) == 0:
        score += 0.1
    if int(evidence_row.get("unresolved_evidence_count") or 0) == 0:
        score += 0.1
    return (round(min(1.0, score), 6), "present")


def _component_from_information_gain(
    *,
    source_hypothesis_id: str,
    router_row: dict[str, Any] | None,
    information_gain_by_hypothesis: dict[str, float],
) -> tuple[float, str]:
    if source_hypothesis_id in information_gain_by_hypothesis:
        return (information_gain_by_hypothesis[source_hypothesis_id], "present")
    if isinstance(router_row, dict):
        proxy = ((router_row.get("routing_context_only") or {}).get("score_components") or {}).get(
            "information_gain_proxy_score"
        )
        if isinstance(proxy, (int, float)):
            return (opportunity_value.bounded_float(proxy), "derived_proxy")
    return (0.0, "missing")


def _component_from_compute_efficiency(
    *,
    source_hypothesis_id: str,
    router_row: dict[str, Any] | None,
    source_catalog: dict[str, dict[str, Any]],
) -> tuple[float, str]:
    if isinstance(router_row, dict):
        penalty = ((router_row.get("routing_context_only") or {}).get("score_components") or {}).get(
            "compute_cost_penalty"
        )
        if isinstance(penalty, (int, float)):
            return (round(1.0 - opportunity_value.bounded_float(penalty), 6), "derived_proxy")
    cost_class = _text((source_catalog.get(source_hypothesis_id) or {}).get("cost_class"))
    mapping = {
        "low": 1.0,
        "medium": 0.65,
        "high": 0.35,
    }
    if cost_class in mapping:
        return (mapping[cost_class], "derived_proxy")
    return (0.0, "missing")


def _component_from_data_readiness(
    *,
    registry_row: dict[str, Any],
    evidence_row: dict[str, Any] | None,
    breadth_row: dict[str, Any] | None,
    source_rows: list[tuple[dict[str, Any], str]],
) -> tuple[float, str]:
    blocked_requirements = [
        _text(value)
        for value in registry_row.get("source_requirements") or []
        if _text(value).startswith("blocked:")
    ]
    blockers = [
        _text(value)
        for value in ((breadth_row or {}).get("blocker_reasons") or [])
        if _text(value) in {
            "source_quality_rows_missing",
            "cache_coverage_missing",
            "source_identity_blocked",
        }
    ]
    if blocked_requirements or blockers:
        return (0.0, "blocked")
    if source_rows:
        ready_count = sum(bool(row.get("source_quality_ready")) for row, _ in source_rows)
        score = round(ready_count / max(1, len(source_rows)), 6)
        return (score, "present")
    if isinstance(evidence_row, dict) and int(evidence_row.get("unresolved_evidence_count") or 0) > 0:
        return (0.0, "blocked")
    return (0.0, "missing")


def _recommended_next_action(
    *,
    thesis_status: str,
    priority_band: str,
    component_statuses: dict[str, str],
) -> str:
    if thesis_status in {"blocked", "deprecated"} or priority_band == "blocked":
        return "keep_fail_closed"
    if component_statuses["data_readiness"] in {"blocked", "missing"}:
        return "resolve_data_readiness"
    if component_statuses["historical_evidence"] in {"missing", "blocked"} or component_statuses[
        "information_gain"
    ] == "missing":
        return "increase_evidence_density"
    if priority_band in {"medium", "high"} and thesis_status == "research_ready":
        return "advance_to_routing_comparison"
    return "operator_review_context_only"


def validate_opportunity_row(row: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    missing = [field for field in ROW_REQUIRED_FIELDS if field not in row]
    if missing:
        reasons.append("missing_required_fields")
    if _text(row.get("priority_band")) not in opportunity_value.PRIORITY_BAND_VALUES:
        reasons.append("invalid_priority_band")
    if _text(row.get("recommended_next_action")) not in NEXT_ACTION_VALUES:
        reasons.append("invalid_recommended_next_action")
    component_scores = row.get("component_scores")
    component_statuses = row.get("component_statuses")
    if not isinstance(component_scores, dict) or set(component_scores.keys()) != set(
        opportunity_value.COMPONENT_NAMES
    ):
        reasons.append("invalid_component_scores")
    if not isinstance(component_statuses, dict) or set(component_statuses.keys()) != set(
        opportunity_value.COMPONENT_NAMES
    ):
        reasons.append("invalid_component_statuses")
    for status in (component_statuses or {}).values():
        if status not in opportunity_value.COMPONENT_AVAILABILITY_VALUES:
            reasons.append("invalid_component_status_value")
            break
    for value in (component_scores or {}).values():
        if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            reasons.append("invalid_component_score_value")
            break
    authority = row.get("authority") or {}
    if authority.get("can_generate_executable_strategy") is not False:
        reasons.append("invalid_strategy_generation_authority")
    if authority.get("can_register_strategy") is not False:
        reasons.append("invalid_strategy_registration_authority")
    if authority.get("can_launch_campaign") is not False:
        reasons.append("invalid_campaign_authority")
    return {
        "valid": not reasons,
        "rejection_reasons": sorted(set(reasons)),
    }


def build_opportunity_research_value(
    *,
    repo_root: Path | None = None,
    registry_report: dict[str, Any] | None = None,
    evidence_report: dict[str, Any] | None = None,
    prior_failure_report: dict[str, Any] | None = None,
    breadth_report: dict[str, Any] | None = None,
    source_authority_report: dict[str, Any] | None = None,
    router_report: dict[str, Any] | None = None,
    discovery_digest: dict[str, Any] | None = None,
    information_gain_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry_report = registry_report or _read_json(root / DEFAULT_REGISTRY_PATH)
    evidence_report = evidence_report or _read_json(root / DEFAULT_EVIDENCE_PATH)
    prior_failure_report = prior_failure_report or _read_json(root / DEFAULT_PRIOR_FAILURE_PATH)
    breadth_report = breadth_report or _read_json(root / DEFAULT_BREADTH_PATH)
    source_authority_report = source_authority_report or _read_json(root / DEFAULT_SOURCE_AUTHORITY_PATH)
    router_report = router_report or _read_json(root / DEFAULT_ROUTER_PATH)
    discovery_digest = discovery_digest or _read_json(root / DEFAULT_DISCOVERY_DIGEST_PATH)
    information_gain_report = information_gain_report or _read_json(root / DEFAULT_INFORMATION_GAIN_PATH)

    registry_rows = _read_rows(registry_report, "rows")
    evidence_index = {
        _text(row.get("thesis_id")): dict(row)
        for row in _read_rows(evidence_report, "rows")
        if _text(row.get("thesis_id"))
    }
    prior_index = {
        _text(row.get("thesis_id")): dict(row)
        for row in _read_rows(prior_failure_report, "rows")
        if _text(row.get("thesis_id"))
    }
    breadth_rows = _read_rows(breadth_report, "coverage_matrix")
    source_rows = _read_rows(source_authority_report, "rows")
    router_rows = _read_rows(router_report, "eligible_directions")
    discovery_index = _discovery_index(discovery_digest)
    information_gain_by_hypothesis = _information_gain_index(information_gain_report)
    source_catalog = _source_catalog_index()

    family_counts: dict[str, int] = {}
    for row in registry_rows:
        family = _text(row.get("behavior_family"))
        if family:
            family_counts[family] = family_counts.get(family, 0) + 1

    rows: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    duplicate_signature_count = 0

    for registry_row in sorted(registry_rows, key=lambda item: _text(item.get("thesis_id"))):
        thesis_id = _text(registry_row.get("thesis_id"))
        thesis_status = _text(registry_row.get("status"))
        behavior_family = _text(registry_row.get("behavior_family"))
        source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
        evidence_row = evidence_index.get(thesis_id)
        prior_row = prior_index.get(thesis_id)
        breadth_row, breadth_ref = _match_breadth_row(breadth_rows, registry_row)
        matched_source_rows = _matching_source_authority_rows(source_rows, registry_row)
        router_row, router_ref = _matching_router_row(router_rows, registry_row)
        discovery_row = discovery_index.get(source_hypothesis_id)

        component_scores = {
            "thesis_readiness": _component_from_thesis_status(thesis_status)[0],
            "data_readiness": _component_from_data_readiness(
                registry_row=registry_row,
                evidence_row=evidence_row,
                breadth_row=breadth_row,
                source_rows=matched_source_rows,
            )[0],
            "signal_density": _component_from_signal_density(
                _text(registry_row.get("signal_density_expectation"))
            )[0],
            "behavior_orthogonality": _component_from_orthogonality(
                behavior_family=behavior_family,
                family_counts=family_counts,
            )[0],
            "prior_failure_risk": _component_from_prior_failure(prior_row)[0],
            "null_control_feasibility": _component_from_null_controls(
                tuple(registry_row.get("null_controls") or ())
            )[0],
            "regime_coverage": _component_from_regime_coverage(breadth_row)[0],
            "historical_evidence": _component_from_historical_evidence(
                evidence_row,
                breadth_row,
            )[0],
            "information_gain": _component_from_information_gain(
                source_hypothesis_id=source_hypothesis_id,
                router_row=router_row,
                information_gain_by_hypothesis=information_gain_by_hypothesis,
            )[0],
            "compute_efficiency": _component_from_compute_efficiency(
                source_hypothesis_id=source_hypothesis_id,
                router_row=router_row,
                source_catalog=source_catalog,
            )[0],
        }
        component_statuses = {
            "thesis_readiness": _component_from_thesis_status(thesis_status)[1],
            "data_readiness": _component_from_data_readiness(
                registry_row=registry_row,
                evidence_row=evidence_row,
                breadth_row=breadth_row,
                source_rows=matched_source_rows,
            )[1],
            "signal_density": _component_from_signal_density(
                _text(registry_row.get("signal_density_expectation"))
            )[1],
            "behavior_orthogonality": _component_from_orthogonality(
                behavior_family=behavior_family,
                family_counts=family_counts,
            )[1],
            "prior_failure_risk": _component_from_prior_failure(prior_row)[1],
            "null_control_feasibility": _component_from_null_controls(
                tuple(registry_row.get("null_controls") or ())
            )[1],
            "regime_coverage": _component_from_regime_coverage(breadth_row)[1],
            "historical_evidence": _component_from_historical_evidence(
                evidence_row,
                breadth_row,
            )[1],
            "information_gain": _component_from_information_gain(
                source_hypothesis_id=source_hypothesis_id,
                router_row=router_row,
                information_gain_by_hypothesis=information_gain_by_hypothesis,
            )[1],
            "compute_efficiency": _component_from_compute_efficiency(
                source_hypothesis_id=source_hypothesis_id,
                router_row=router_row,
                source_catalog=source_catalog,
            )[1],
        }

        signature = _text(registry_row.get("duplicate_signature"))
        duplicate_detected = False
        if signature:
            if signature in seen_signatures:
                duplicate_signature_count += 1
                duplicate_detected = True
            seen_signatures.add(signature)

        opportunity_score = opportunity_value.weighted_opportunity_score(component_scores)
        blocked = thesis_status in {"blocked", "deprecated"} or duplicate_detected
        priority_band = opportunity_value.priority_band(opportunity_score, blocked=blocked)
        recommended_next_action = _recommended_next_action(
            thesis_status=thesis_status,
            priority_band=priority_band,
            component_statuses=component_statuses,
        )
        provenance = list(registry_row.get("provenance_refs") or [])
        if evidence_row:
            provenance.extend(evidence_row.get("provenance_refs") or [])
        if prior_row:
            provenance.extend(prior_row.get("provenance_refs") or [])
        if breadth_ref:
            provenance.append(breadth_ref)
        provenance.extend(ref for _, ref in matched_source_rows)
        if router_ref:
            provenance.append(router_ref)
        if discovery_row:
            provenance.append(DEFAULT_DISCOVERY_DIGEST_PATH.as_posix())
        if source_hypothesis_id in information_gain_by_hypothesis:
            provenance.append(DEFAULT_INFORMATION_GAIN_PATH.as_posix())

        row = {
            "thesis_id": thesis_id,
            "source_hypothesis_id": source_hypothesis_id,
            "behavior_family": behavior_family,
            "thesis_status": thesis_status,
            "opportunity_score": opportunity_score,
            "priority_band": priority_band,
            "recommended_next_action": recommended_next_action,
            "component_scores": opportunity_value.canonical_component_scores(component_scores),
            "component_statuses": dict(sorted(component_statuses.items())),
            "legacy_discovery_opportunity_score": (
                ((discovery_row.get("score") or {}).get("opportunity_probability_score"))
                if isinstance(discovery_row, dict)
                else None
            ),
            "legacy_discovery_semantics": (
                "proposal_only_expected_research_value_not_authority"
                if isinstance(discovery_row, dict)
                else "missing"
            ),
            "duplicate_signature": signature,
            "duplicate_detected": duplicate_detected,
            "provenance_refs": list(_unique(provenance)),
            "schema_version": SCHEMA_VERSION,
            "authority": {
                "can_generate_executable_strategy": False,
                "can_register_strategy": False,
                "can_promote_candidate": False,
                "can_launch_campaign": False,
                "can_activate_paper_shadow_live": False,
                "evidence_authority": "context_only",
            },
        }
        validation = validate_opportunity_row(row)
        validations.append(
            {
                "thesis_id": thesis_id,
                "valid": validation["valid"],
                "rejection_reasons": list(validation["rejection_reasons"]),
            }
        )
        rows.append(row)

    invalid_count = sum(1 for row in validations if not row["valid"])
    rows.sort(key=lambda item: (-float(item["opportunity_score"]), _text(item["thesis_id"])))

    summary = {
        "thesis_count": len(rows),
        "invalid_row_count": invalid_count,
        "duplicate_signature_count": duplicate_signature_count,
        "by_priority_band": {
            band: sum(row["priority_band"] == band for row in rows)
            for band in opportunity_value.PRIORITY_BAND_VALUES
        },
        "by_next_action": {
            action: sum(row["recommended_next_action"] == action for row in rows)
            for action in NEXT_ACTION_VALUES
        },
        "routing_comparison_ready_count": sum(
            row["recommended_next_action"] == "advance_to_routing_comparison"
            for row in rows
        ),
        "final_recommendation": (
            "opportunity_research_value_ready"
            if invalid_count == 0 and duplicate_signature_count == 0
            else "opportunity_research_value_blocked"
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "artifact_references": {
            "behavior_thesis_registry": DEFAULT_REGISTRY_PATH.as_posix(),
            "behavior_thesis_evidence": DEFAULT_EVIDENCE_PATH.as_posix(),
            "prior_failure_retrieval": DEFAULT_PRIOR_FAILURE_PATH.as_posix(),
            "evidence_breadth_framework": DEFAULT_BREADTH_PATH.as_posix(),
            "source_identity_authority_normalization": DEFAULT_SOURCE_AUTHORITY_PATH.as_posix(),
            "research_cycle_router": DEFAULT_ROUTER_PATH.as_posix(),
            "hypothesis_discovery_digest": DEFAULT_DISCOVERY_DIGEST_PATH.as_posix(),
            "information_gain": DEFAULT_INFORMATION_GAIN_PATH.as_posix(),
        },
        "score_semantics": "expected_research_value_not_alpha_probability",
        "rows": rows,
        "validations": validations,
        "summary": summary,
        "safety_invariants": {
            "proposal_only_not_authority": True,
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_doc(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Opportunity Research Value",
        "",
        "This surface is read-only. It scores expected research value for prioritization only.",
        "",
        "It does not generate executable strategies, register strategies, promote candidates, or launch campaigns.",
        "",
        f"- status: `{report['summary']['final_recommendation']}`",
        f"- thesis_count: `{report['summary']['thesis_count']}`",
        f"- invalid_row_count: `{report['summary']['invalid_row_count']}`",
        f"- duplicate_signature_count: `{report['summary']['duplicate_signature_count']}`",
        f"- routing_comparison_ready_count: `{report['summary']['routing_comparison_ready_count']}`",
        "",
        "| thesis_id | behavior_family | priority_band | opportunity_score | next_action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("thesis_id")),
                    _text(row.get("behavior_family")),
                    _text(row.get("priority_band")),
                    f"{float(row.get('opportunity_score') or 0.0):.3f}",
                    _text(row.get("recommended_next_action")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Legacy hypothesis-discovery opportunity scores remain proposal-only context when present.",
            "Missing information-gain or discovery-digest artifacts fail closed and do not create authority.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    report: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, str]:
    root = repo_root or Path.cwd()
    latest = root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    doc = root / DOC_PATH
    latest.parent.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    for path in (latest, doc):
        _validate_write_target(path)
    payload = json.dumps(report, indent=2, sort_keys=True)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)
    doc.write_text(render_doc(report), encoding="utf-8")
    return {
        "latest": latest.relative_to(root).as_posix(),
        "doc": doc.relative_to(root).as_posix(),
    }


def read_opportunity_research_value_status(
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    payload = _read_json(root / DEFAULT_OUTPUT_DIR / LATEST_NAME)
    if not payload:
        return {
            "status": "missing",
            "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
            "fails_closed": True,
        }
    return {
        "status": "ready",
        "path": (DEFAULT_OUTPUT_DIR / LATEST_NAME).as_posix(),
        "fails_closed": False,
        "schema_version": payload.get("schema_version"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_opportunity_research_value_status(), indent=2, sort_keys=True))
        return 0

    report = build_opportunity_research_value()
    if args.write:
        result = write_outputs(report)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
