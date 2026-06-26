from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from research.hypothesis_discovery.behavior_catalog import get_behavior as get_discovery_behavior
from research.qre_behavior_catalog import get_behavior_family, list_behavior_families
from research.strategy_hypothesis_catalog import STRATEGY_HYPOTHESIS_CATALOG, StrategyHypothesis


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_behavior_thesis_registry"
MODULE_VERSION: Final[str] = "ade-qre-017l-2026-06-26"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_behavior_thesis_registry")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_behavior_thesis_registry.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_behavior_thesis_registry/",
    "docs/governance/qre_behavior_thesis_registry.md",
)
DEFAULT_DISPOSITION_MEMORY_PATH: Final[Path] = Path(
    "logs/qre_hypothesis_disposition_memory/latest.json"
)

THESIS_STATUS_VALUES: Final[tuple[str, ...]] = (
    "draft",
    "research_ready",
    "blocked",
    "deprecated",
)
SIGNAL_DENSITY_VALUES: Final[tuple[str, ...]] = (
    "unknown",
    "sparse",
    "moderate",
    "dense",
    "blocked",
)
REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "thesis_id",
    "title",
    "behavior_family",
    "mechanism",
    "expected_behavior",
    "universe",
    "timeframe",
    "regime_context",
    "falsification_plan",
    "minimum_sample",
    "signal_density_expectation",
    "screening_plan",
    "validation_plan",
    "oos_plan",
    "null_controls",
    "data_requirements",
    "source_requirements",
    "supporting_evidence",
    "contradicting_evidence",
    "prior_similar_failures",
    "status",
    "created_at_equivalent",
    "schema_version",
)
SOURCE_STATUS_TO_THESIS_STATUS: Final[dict[str, str]] = {
    "active_discovery": "research_ready",
    "planned": "draft",
    "disabled": "blocked",
    "diagnostic": "blocked",
}
STRATEGY_FAMILY_TO_BEHAVIOR_ID: Final[dict[str, str]] = {
    "trend_pullback": "pullback_continuation",
    "volatility_compression_breakout": "volatility_compression_breakout",
    "atr_adaptive_trend": "trend_continuation",
    "multi_asset_trend_sleeve": "trend_continuation",
    "cross_sectional_momentum": "relative_strength",
    "dynamic_pairs": "mean_reversion",
    "regime_diagnostics": "index_regime_filter",
}
ACTIVE_DISCOVERY_NULL_CONTROLS: Final[dict[str, tuple[str, ...]]] = {
    "trend_pullback": ("qre_null_control_falsification_suite",),
    "volatility_compression_breakout": ("qre_null_control_falsification_suite",),
}


@dataclass(frozen=True)
class BehaviorThesis:
    thesis_id: str
    title: str
    behavior_family: str
    mechanism: str
    expected_behavior: str
    universe: str
    timeframe: str
    regime_context: str
    falsification_plan: tuple[str, ...]
    minimum_sample: str
    signal_density_expectation: str
    screening_plan: tuple[str, ...]
    validation_plan: tuple[str, ...]
    oos_plan: tuple[str, ...]
    null_controls: tuple[str, ...]
    data_requirements: tuple[str, ...]
    source_requirements: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    prior_similar_failures: tuple[str, ...]
    status: str
    created_at_equivalent: str
    schema_version: str = SCHEMA_VERSION
    source_hypothesis_id: str = ""
    strategy_family: str = ""
    duplicate_signature: str = ""
    provenance_refs: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "thesis_id": self.thesis_id,
            "title": self.title,
            "behavior_family": self.behavior_family,
            "mechanism": self.mechanism,
            "expected_behavior": self.expected_behavior,
            "universe": self.universe,
            "timeframe": self.timeframe,
            "regime_context": self.regime_context,
            "falsification_plan": list(self.falsification_plan),
            "minimum_sample": self.minimum_sample,
            "signal_density_expectation": self.signal_density_expectation,
            "screening_plan": list(self.screening_plan),
            "validation_plan": list(self.validation_plan),
            "oos_plan": list(self.oos_plan),
            "null_controls": list(self.null_controls),
            "data_requirements": list(self.data_requirements),
            "source_requirements": list(self.source_requirements),
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "prior_similar_failures": list(self.prior_similar_failures),
            "status": self.status,
            "created_at_equivalent": self.created_at_equivalent,
            "schema_version": self.schema_version,
            "source_hypothesis_id": self.source_hypothesis_id,
            "strategy_family": self.strategy_family,
            "duplicate_signature": self.duplicate_signature,
            "provenance_refs": list(self.provenance_refs),
            "authority": {
                "can_generate_executable_strategy": False,
                "can_register_strategy": False,
                "can_promote_candidate": False,
                "can_launch_campaign": False,
                "can_activate_paper_shadow_live": False,
                "evidence_authority": "context_only",
            },
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique(values: tuple[str, ...] | list[str] | tuple[Any, ...] | list[Any]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_behavior_thesis_registry: refusing write outside allowlist: {path!r}"
        )


def _sha(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _deterministic_thesis_id(hypothesis: StrategyHypothesis, behavior_id: str) -> str:
    digest = _sha(
        {
            "hypothesis_id": hypothesis.hypothesis_id,
            "strategy_family": hypothesis.strategy_family,
            "behavior_id": behavior_id,
        }
    )
    return f"qbt_{digest[:16]}"


def _duplicate_signature(payload: dict[str, Any]) -> str:
    return _sha(
        {
            "behavior_family": payload.get("behavior_family"),
            "mechanism": payload.get("mechanism"),
            "expected_behavior": payload.get("expected_behavior"),
            "universe": payload.get("universe"),
            "timeframe": payload.get("timeframe"),
            "regime_context": payload.get("regime_context"),
            "falsification_plan": payload.get("falsification_plan"),
            "null_controls": payload.get("null_controls"),
            "data_requirements": payload.get("data_requirements"),
            "source_requirements": payload.get("source_requirements"),
        }
    )


def _matching_disposition_rows(
    payload: dict[str, Any] | None,
    *,
    hypothesis_id: str,
    behavior_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    record = payload.get("record")
    rows = [record] if isinstance(record, dict) else []
    matches: list[dict[str, Any]] = []
    for row in rows:
        row_hypothesis_id = _text(row.get("hypothesis_id"))
        row_behavior_id = _text(row.get("behavior_id"))
        if row_hypothesis_id == hypothesis_id or row_behavior_id == behavior_id:
            matches.append(dict(row))
    return matches


def _explicit_missing(label: str) -> tuple[str, ...]:
    return (f"none_recorded:{label}",)


def _contradicting_evidence(disposition_rows: list[dict[str, Any]]) -> tuple[str, ...]:
    refs: list[str] = []
    for row in disposition_rows:
        record_id = _text(row.get("memory_record_id")) or "record"
        refs.append(
            "logs/qre_hypothesis_disposition_memory/latest.json"
            f"#record::{record_id}"
        )
    return _unique(refs) if refs else _explicit_missing("contradicting_evidence")


def _prior_failures(disposition_rows: list[dict[str, Any]]) -> tuple[str, ...]:
    failures: list[str] = []
    for row in disposition_rows:
        for value in row.get("failure_classes") or []:
            text = _text(value)
            if text:
                failures.append(text)
    return _unique(failures) if failures else _explicit_missing("prior_similar_failures")


def _signal_density_expectation(hypothesis: StrategyHypothesis) -> str:
    if hypothesis.status in {"disabled", "diagnostic"}:
        return "blocked"
    if hypothesis.cost_class == "high":
        return "sparse"
    if hypothesis.cost_class == "low":
        return "dense"
    return "moderate"


def _status(hypothesis: StrategyHypothesis, behavior_status: str) -> str:
    status = SOURCE_STATUS_TO_THESIS_STATUS[hypothesis.status]
    if behavior_status == "deprecated":
        return "deprecated"
    if behavior_status == "blocked":
        return "blocked"
    return status


def _timeframe(behavior_id: str) -> str:
    behavior = get_behavior_family(behavior_id)
    return "|".join(behavior.typical_timeframes)


def _active_plan(label: str, hypothesis_id: str) -> tuple[str, ...]:
    return (
        f"use_existing_hypothesis_bridge:{hypothesis_id}",
        f"preserve_read_only_{label}_authority_boundary",
        "fail_closed_when_required_evidence_is_missing",
    )


def _blocked_plan(label: str, reason: str) -> tuple[str, ...]:
    return (f"blocked:{label}:{reason}",)


def _minimum_sample(thesis_status: str) -> str:
    if thesis_status == "research_ready":
        return "campaign_specific_minimum_sample_required_before_support"
    if thesis_status == "deprecated":
        return "blocked:deprecated_behavior_family"
    return "blocked:minimum_sample_not_defined_until_research_ready"


def _universe(hypothesis: StrategyHypothesis) -> str:
    if hypothesis.status == "active_discovery":
        return "existing_preset_bound_universes_only"
    return "blocked:campaign_scope_pending_registry_maturation"


def _regime_context(hypothesis: StrategyHypothesis, behavior_id: str) -> str:
    behavior = get_behavior_family(behavior_id)
    if hypothesis.status == "active_discovery":
        return (
            f"bounded_existing_research_scope:{behavior.display_name.lower().replace(' ', '_')}"
        )
    return f"blocked:regime_context_pending:{behavior.status}"


def _null_controls(hypothesis: StrategyHypothesis, thesis_status: str) -> tuple[str, ...]:
    if thesis_status != "research_ready":
        return _blocked_plan("null_controls", "behavior_not_research_ready")
    if hypothesis.strategy_family in ACTIVE_DISCOVERY_NULL_CONTROLS:
        discovery_behavior = get_discovery_behavior(hypothesis.strategy_family)
        return _unique(
            (discovery_behavior.required_null_model,)
            + ACTIVE_DISCOVERY_NULL_CONTROLS[hypothesis.strategy_family]
        )
    return ("qre_null_control_falsification_suite",)


def _supporting_evidence(
    hypothesis: StrategyHypothesis,
    behavior_id: str,
    *,
    include_discovery_bridge: bool,
) -> tuple[str, ...]:
    refs = [
        f"research/strategy_hypothesis_catalog.py#{hypothesis.hypothesis_id}",
        f"research/qre_behavior_catalog.py#{behavior_id}",
        "docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md#ade-qre-017l",
    ]
    if include_discovery_bridge:
        refs.append(
            f"research/hypothesis_discovery/behavior_catalog.py#{hypothesis.strategy_family}"
        )
    return _unique(refs)


def _mechanism(hypothesis: StrategyHypothesis, behavior_id: str) -> str:
    behavior = get_behavior_family(behavior_id)
    return " ".join(
        part
        for part in (
            behavior.description,
            _text(hypothesis.description),
        )
        if part
    )


def _expected_behavior(behavior_id: str) -> str:
    behavior = get_behavior_family(behavior_id)
    return "; ".join(behavior.expected_observables)


def _falsification_plan(
    hypothesis: StrategyHypothesis,
    behavior_id: str,
    thesis_status: str,
) -> tuple[str, ...]:
    behavior = get_behavior_family(behavior_id)
    if thesis_status != "research_ready":
        return _blocked_plan("falsification", "thesis_not_research_ready")
    values = list(behavior.common_failure_modes) + list(hypothesis.expected_failure_modes)
    values.append("require_contradictions_to_remain_visible")
    return _unique(values)


def _data_requirements(hypothesis: StrategyHypothesis, behavior_id: str) -> tuple[str, ...]:
    behavior = get_behavior_family(behavior_id)
    return _unique(
        list(behavior.required_data_capabilities)
        + list(hypothesis.feature_dependencies)
        + ["reason_record_lineage"]
    )


def _source_requirements(thesis_status: str, behavior_id: str) -> tuple[str, ...]:
    behavior = get_behavior_family(behavior_id)
    base = list(behavior.evidence_requirements) + [
        "qre_data_source_quality_readiness",
        "qre_data_cache_manifest",
    ]
    if thesis_status != "research_ready":
        base.append("blocked:source_requirements_not_satisfied_for_execution")
    return _unique(base)


def build_behavior_thesis(
    hypothesis: StrategyHypothesis,
    *,
    disposition_payload: dict[str, Any] | None = None,
) -> BehaviorThesis:
    behavior_id = STRATEGY_FAMILY_TO_BEHAVIOR_ID[hypothesis.strategy_family]
    behavior = get_behavior_family(behavior_id)
    thesis_status = _status(hypothesis, behavior.status)
    include_discovery_bridge = hypothesis.strategy_family in ACTIVE_DISCOVERY_NULL_CONTROLS
    disposition_rows = _matching_disposition_rows(
        disposition_payload,
        hypothesis_id=hypothesis.hypothesis_id,
        behavior_id=behavior_id,
    )
    payload = {
        "thesis_id": _deterministic_thesis_id(hypothesis, behavior_id),
        "title": f"{behavior.display_name}: {hypothesis.hypothesis_id}",
        "behavior_family": behavior_id,
        "mechanism": _mechanism(hypothesis, behavior_id),
        "expected_behavior": _expected_behavior(behavior_id),
        "universe": _universe(hypothesis),
        "timeframe": _timeframe(behavior_id),
        "regime_context": _regime_context(hypothesis, behavior_id),
        "falsification_plan": list(
            _falsification_plan(hypothesis, behavior_id, thesis_status)
        ),
        "minimum_sample": _minimum_sample(thesis_status),
        "signal_density_expectation": _signal_density_expectation(hypothesis),
        "screening_plan": list(
            _active_plan("screening", hypothesis.hypothesis_id)
            if thesis_status == "research_ready"
            else _blocked_plan("screening", "thesis_not_research_ready")
        ),
        "validation_plan": list(
            _active_plan("validation", hypothesis.hypothesis_id)
            if thesis_status == "research_ready"
            else _blocked_plan("validation", "thesis_not_research_ready")
        ),
        "oos_plan": list(
            _active_plan("oos", hypothesis.hypothesis_id)
            if thesis_status == "research_ready"
            else _blocked_plan("oos", "thesis_not_research_ready")
        ),
        "null_controls": list(_null_controls(hypothesis, thesis_status)),
        "data_requirements": list(_data_requirements(hypothesis, behavior_id)),
        "source_requirements": list(_source_requirements(thesis_status, behavior_id)),
        "supporting_evidence": list(
            _supporting_evidence(
                hypothesis,
                behavior_id,
                include_discovery_bridge=include_discovery_bridge,
            )
        ),
        "contradicting_evidence": list(_contradicting_evidence(disposition_rows)),
        "prior_similar_failures": list(_prior_failures(disposition_rows)),
        "status": thesis_status,
        "created_at_equivalent": (
            f"research/strategy_hypothesis_catalog.py#{hypothesis.hypothesis_id}"
        ),
        "schema_version": SCHEMA_VERSION,
        "source_hypothesis_id": hypothesis.hypothesis_id,
        "strategy_family": hypothesis.strategy_family,
        "provenance_refs": list(
            _unique(
                list(
                    _supporting_evidence(
                        hypothesis,
                        behavior_id,
                        include_discovery_bridge=include_discovery_bridge,
                    )
                )
                + ["logs/qre_hypothesis_disposition_memory/latest.json"]
            )
        ),
    }
    payload["duplicate_signature"] = _duplicate_signature(payload)
    return BehaviorThesis(
        thesis_id=_text(payload["thesis_id"]),
        title=_text(payload["title"]),
        behavior_family=_text(payload["behavior_family"]),
        mechanism=_text(payload["mechanism"]),
        expected_behavior=_text(payload["expected_behavior"]),
        universe=_text(payload["universe"]),
        timeframe=_text(payload["timeframe"]),
        regime_context=_text(payload["regime_context"]),
        falsification_plan=_unique(payload["falsification_plan"]),
        minimum_sample=_text(payload["minimum_sample"]),
        signal_density_expectation=_text(payload["signal_density_expectation"]),
        screening_plan=_unique(payload["screening_plan"]),
        validation_plan=_unique(payload["validation_plan"]),
        oos_plan=_unique(payload["oos_plan"]),
        null_controls=_unique(payload["null_controls"]),
        data_requirements=_unique(payload["data_requirements"]),
        source_requirements=_unique(payload["source_requirements"]),
        supporting_evidence=_unique(payload["supporting_evidence"]),
        contradicting_evidence=_unique(payload["contradicting_evidence"]),
        prior_similar_failures=_unique(payload["prior_similar_failures"]),
        status=_text(payload["status"]),
        created_at_equivalent=_text(payload["created_at_equivalent"]),
        schema_version=SCHEMA_VERSION,
        source_hypothesis_id=_text(payload["source_hypothesis_id"]),
        strategy_family=_text(payload["strategy_family"]),
        duplicate_signature=_text(payload["duplicate_signature"]),
        provenance_refs=_unique(payload["provenance_refs"]),
    )


def validate_behavior_thesis(
    thesis: BehaviorThesis | dict[str, Any],
    *,
    duplicate_signatures: set[str] | None = None,
) -> dict[str, Any]:
    payload = thesis.to_payload() if isinstance(thesis, BehaviorThesis) else dict(thesis)
    rejections: list[str] = []
    missing = [field for field in REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        rejections.append("missing_required_fields")
    if _text(payload.get("behavior_family")) not in {
        row.behavior_id for row in list_behavior_families()
    }:
        rejections.append("unknown_behavior_family")
    if _text(payload.get("status")) not in THESIS_STATUS_VALUES:
        rejections.append("invalid_status")
    if _text(payload.get("signal_density_expectation")) not in SIGNAL_DENSITY_VALUES:
        rejections.append("invalid_signal_density_expectation")
    if _text(payload.get("schema_version")) != SCHEMA_VERSION:
        rejections.append("invalid_schema_version")
    if not payload.get("supporting_evidence"):
        rejections.append("missing_supporting_evidence")
    if not payload.get("contradicting_evidence"):
        rejections.append("missing_contradicting_evidence_state")
    if not payload.get("prior_similar_failures"):
        rejections.append("missing_prior_failure_state")
    if _text(payload.get("status")) == "research_ready":
        for field in (
            "falsification_plan",
            "screening_plan",
            "validation_plan",
            "oos_plan",
            "null_controls",
        ):
            values = payload.get(field) or []
            if not isinstance(values, list) or any(str(value).startswith("blocked:") for value in values):
                rejections.append(f"research_ready_{field}_blocked")
    if duplicate_signatures and _text(payload.get("duplicate_signature")) in duplicate_signatures:
        rejections.append("duplicate_thesis_signature")
    authority = payload.get("authority") if isinstance(payload.get("authority"), dict) else {}
    if authority.get("can_generate_executable_strategy") is not False:
        rejections.append("strategy_generation_authority_forbidden")
    if authority.get("can_register_strategy") is not False:
        rejections.append("strategy_registration_authority_forbidden")
    if authority.get("can_launch_campaign") is not False:
        rejections.append("campaign_authority_forbidden")
    return {
        "valid": not rejections,
        "rejection_reasons": list(dict.fromkeys(rejections)),
        "duplicate_signature": _text(payload.get("duplicate_signature")),
        "thesis_id": _text(payload.get("thesis_id")),
        "status": _text(payload.get("status")),
    }


def build_behavior_thesis_registry(
    *,
    repo_root: Path = Path("."),
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
    disposition_memory_path: Path = DEFAULT_DISPOSITION_MEMORY_PATH,
) -> dict[str, Any]:
    disposition_payload = _read_json(repo_root / disposition_memory_path)
    theses = [
        build_behavior_thesis(hypothesis, disposition_payload=disposition_payload)
        for hypothesis in sorted(catalog, key=lambda row: row.hypothesis_id)
    ]
    payload_rows = sorted(
        (row.to_payload() for row in theses),
        key=lambda row: _text(row.get("thesis_id")),
    )
    signatures = [row["duplicate_signature"] for row in payload_rows]
    duplicate_signatures = {
        signature for signature in signatures if signatures.count(signature) > 1
    }
    validations = [
        validate_behavior_thesis(row, duplicate_signatures=duplicate_signatures)
        for row in theses
    ]
    row_status_counts: dict[str, int] = {}
    for row in payload_rows:
        row_status_counts[row["status"]] = row_status_counts.get(row["status"], 0) + 1
    invalid_rows = [row for row in validations if not row["valid"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "rows": payload_rows,
        "summary": {
            "status": "ready" if not invalid_rows else "not_ready",
            "research_ready": not invalid_rows,
            "thesis_count": len(payload_rows),
            "invalid_thesis_count": len(invalid_rows),
            "duplicate_signature_count": len(duplicate_signatures),
            "source_hypothesis_count": len(catalog),
            "row_status_counts": dict(sorted(row_status_counts.items())),
            "blocking_reasons": sorted(
                {
                    reason
                    for row in invalid_rows
                    for reason in row["rejection_reasons"]
                }
            ),
            "operator_summary": (
                "The behavior thesis registry is deterministic, read-only, and non-authoritative. "
                "It requires future hypothesis-family, preset, campaign, and synthesis design work "
                "to name an explicit thesis before expansion."
            ),
            "final_recommendation": (
                "behavior_thesis_registry_ready"
                if not invalid_rows
                else "repair_behavior_thesis_registry_contract_gaps"
            ),
        },
        "validations": validations,
        "artifact_references": {
            "strategy_hypothesis_catalog": "research/strategy_hypothesis_catalog.py",
            "behavior_catalog": "research/qre_behavior_catalog.py",
            "disposition_memory": disposition_memory_path.as_posix(),
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Behavior Thesis Registry",
        "",
        "This surface is read-only. It does not generate executable strategies, register strategies, promote candidates, or launch campaigns.",
        "",
        f"- status: `{_text(summary.get('status'))}`",
        f"- thesis_count: `{int(summary.get('thesis_count') or 0)}`",
        f"- invalid_thesis_count: `{int(summary.get('invalid_thesis_count') or 0)}`",
        f"- duplicate_signature_count: `{int(summary.get('duplicate_signature_count') or 0)}`",
        f"- final_recommendation: `{_text(summary.get('final_recommendation'))}`",
        "",
        "| thesis_id | behavior_family | source_hypothesis_id | status | signal_density_expectation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("thesis_id")),
                    _text(row.get("behavior_family")),
                    _text(row.get("source_hypothesis_id")),
                    _text(row.get("status")),
                    _text(row.get("signal_density_expectation")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Contradictions remain visible as context only. Retrieval and memory may link prior failures, but they do not become evidence authority.",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    doc_path: Path = DOC_PATH,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    latest = repo_root / output_dir / LATEST_NAME
    doc = repo_root / doc_path
    latest.parent.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    _validate_write_target(latest)
    _validate_write_target(doc)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_doc = doc.with_suffix(doc.suffix + ".tmp")
    tmp_doc.write_text(render_markdown(report) + "\n", encoding="utf-8")
    os.replace(tmp_doc, doc)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "doc": doc.relative_to(repo_root).as_posix(),
    }


def read_behavior_thesis_registry_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    path = repo_root / output_dir / LATEST_NAME
    payload = _read_json(path)
    if not payload:
        return {
            "status": "missing_behavior_thesis_registry",
            "research_ready": False,
            "path": path.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "status": _text(summary.get("status")) or "unknown",
        "research_ready": bool(summary.get("research_ready")),
        "path": path.relative_to(repo_root).as_posix(),
        "fails_closed": not bool(summary.get("research_ready")),
        "schema_version": _text(payload.get("schema_version")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_behavior_thesis_registry",
        description="Build the deterministic QRE behavior thesis registry.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_behavior_thesis_registry()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
