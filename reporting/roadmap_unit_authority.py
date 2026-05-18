"""A20c — Roadmap Unit Authority Classifier Integration (read-only).

Per-unit projection that derives a deterministic
``UnitAuthorityDecision`` for every A20b ``ImplementationUnit`` by
calling the canonical Execution Authority classifier
(:func:`reporting.execution_authority.classify`) and aggregating its
verdicts together with A20c's own deterministic evidence rules for
the non-path inputs (``target_layer``, ``risk_class``,
``operator_gate``, ``authority_hint``, ``unit_kind``,
``stop_conditions``).

A20c MUST NOT create a second source of truth for path-level
authority. Every per-file evidence record carries the verbatim
``decision`` / ``reason`` returned by the canonical classifier.
Non-path evidence kinds have their own deterministic, closed-vocab
rules pinned by tests.

Aggregation is a pure max-severity reduction over the **aggregating
evidence kinds**: ``expected_file_classifier``, ``target_layer``,
``risk_class``, ``operator_gate``, ``authority_hint``,
``unit_kind``. The **informational evidence kinds**
(``forbidden_file_classifier``, ``stop_conditions``) are recorded
for transparency but do not elevate the aggregate. Including
forbidden-file decisions in aggregation would force every unit to
``PERMANENTLY_DENIED`` (because every A20b unit's baseline
``forbidden_files`` contains live / frozen / governance paths that
the canonical classifier rightly denies) — that would be
operationally useless and is therefore explicitly excluded.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` (read-only) +
  ``reporting.roadmap_task_units`` (read-only) only.
* No subprocess, no network, no ``gh``, no ``git``, no GitHub API.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_agent_activity_timeline``.
* No LLM, no external API, no fuzzy parsing, no file-content
  parsing of any canonical document at runtime.
* Atomic write only under ``logs/roadmap_unit_authority/``.
* Deterministic output: same upstream + injected
  ``generated_at_utc`` → byte-identical artefact.
* No mutation of A20a or A20b artefacts (pinned by sha256
  before/after tests).
* No runtime / trading / paper / shadow / broker / risk / live
  authority granted. ``permanently_denied=true`` for any unit
  whose evidence touches those surfaces; pinned by tests.
* ``step5_implementation_allowed`` remains ``False``;
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.
* AAC visibility and next-buildable-unit selector remain
  unimplemented; pinned by invariants.

CLI::

    python -m reporting.roadmap_unit_authority
    python -m reporting.roadmap_unit_authority --no-write
    python -m reporting.roadmap_unit_authority --status
    python -m reporting.roadmap_unit_authority --indent 2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import execution_authority as ea
from reporting import roadmap_task_units as rtu

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A20c"
REPORT_KIND: Final[str] = "roadmap_unit_authority"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed final authority classes. Exactly the canonical classifier's
#: ``DECISIONS`` enum, pinned to the same tuple values.
AUTHORITY_CLASS: Final[tuple[str, ...]] = ea.DECISIONS

_AUTO_ALLOWED: Final[str] = ea.DECISION_AUTO_ALLOWED
_NEEDS_HUMAN: Final[str] = ea.DECISION_NEEDS_HUMAN
_PERMANENTLY_DENIED: Final[str] = ea.DECISION_PERMANENTLY_DENIED

#: Severity ordering. Higher value = more restrictive.
_SEVERITY: Final[dict[str, int]] = {
    _AUTO_ALLOWED: 0,
    _NEEDS_HUMAN: 1,
    _PERMANENTLY_DENIED: 2,
}

#: Closed authority reason vocabulary. The first segment mirrors
#: ``reporting.execution_authority.REASONS`` verbatim so per-file
#: evidence carries reasons the canonical classifier itself emits.
#: The second segment carries A20c-specific reasons for the non-path
#: evidence kinds.
_CANONICAL_REASONS: Final[tuple[str, ...]] = ea.REASONS
_A20C_ONLY_REASONS: Final[tuple[str, ...]] = (
    "paper_runtime_activation_not_authorised",
    "shadow_runtime_activation_not_authorised",
    "live_runtime_activation_not_authorised",
    "trading_runtime_activation_not_authorised",
    "operator_gate_required",
    "governance_bootstrap_pr_required",
    "no_protected_or_runtime_surface",
    "fail_closed_unknown_evidence",
    "fail_closed_unknown_risk_class",
    "fail_closed_unknown_target_layer",
    "fail_closed_unknown_operator_gate",
    "fail_closed_unknown_authority_hint",
    "fail_closed_unknown_unit_kind",
    "research_module_requires_human_review",
    "external_intelligence_source_requires_human_review",
    "diagnostic_primitive_requires_human_review",
    "stop_conditions_informational_only",
    "forbidden_file_informational_only",
    "non_path_evidence_baseline",
)
AUTHORITY_REASON: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(_CANONICAL_REASONS + _A20C_ONLY_REASONS)
)

#: Closed evidence-kind vocabulary. Each value names one of the
#: bounded-scalar inputs the spec lists.
AUTHORITY_EVIDENCE_KIND: Final[tuple[str, ...]] = (
    "expected_file_classifier",
    "forbidden_file_classifier",
    "target_layer",
    "risk_class",
    "operator_gate",
    "authority_hint",
    "unit_kind",
    "stop_conditions",
)

#: Evidence kinds that contribute to the unit-level aggregate. The
#: rest are informational only.
_AGGREGATING_EVIDENCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "expected_file_classifier",
        "target_layer",
        "risk_class",
        "operator_gate",
        "authority_hint",
        "unit_kind",
    }
)

_INFORMATIONAL_EVIDENCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "forbidden_file_classifier",
        "stop_conditions",
    }
)

#: Closed projection-status vocabulary.
AUTHORITY_PROJECTION_STATUS: Final[tuple[str, ...]] = (
    "ok",
    "no_units",
    "upstream_unavailable",
    "fail_closed_invariant",
)


# ---------------------------------------------------------------------------
# Evidence sources (for the ``source`` field on each evidence record)
# ---------------------------------------------------------------------------

_SOURCE_CLASSIFIER: Final[str] = "reporting.execution_authority"
_SOURCE_A20C: Final[str] = "reporting.roadmap_unit_authority"


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: Per-evidence record schema.
UNIT_AUTHORITY_EVIDENCE_FIELDS: Final[tuple[str, ...]] = (
    "kind",
    "value",
    "decision",
    "reason",
    "source",
)

#: Per-unit decision schema.
UNIT_AUTHORITY_DECISION_FIELDS: Final[tuple[str, ...]] = (
    "implementation_unit_id",
    "roadmap_task_id",
    "phase",
    "final_authority_class",
    "max_severity",
    "evidence",
    "requires_operator_go",
    "permanently_denied",
    "deny_reasons",
    "classifier_used",
    "fail_closed",
)

#: Top-level projection schema.
UNIT_AUTHORITY_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "source_units_schema_version",
    "authority_decisions",
    "authority_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_EVIDENCE_VALUE_LEN: Final[int] = 300
MAX_REASON_LEN: Final[int] = 80
MAX_DENY_REASONS: Final[int] = 16


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "roadmap_unit_authority"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/roadmap_unit_authority/latest.json"

#: Atomic-write allowlist (POSIX substring form). Any write target
#: not containing this substring is refused with ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/roadmap_unit_authority/"


# ---------------------------------------------------------------------------
# Authority invariants emitted on every projection
# ---------------------------------------------------------------------------

_BASE_AUTHORITY_INVARIANTS: Final[dict[str, bool]] = {
    # A20c flips these from A20b's false values:
    "calls_execution_authority_classifier": True,
    "final_authority_classified": True,
    # Carry forward the authority chain pins:
    "no_runtime_trading_authority": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "writes_only_roadmap_unit_authority_log": True,
    "step5_implementation_allowed": False,
    "mutates_a20a_artifact": False,
    "mutates_a20b_artifact": False,
    "mutates_roadmap_status_fields": False,
    "marks_phase_complete": False,
    "fuzzy_parsing": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    # A20d / A20e still pending:
    "aac_visibility_present": False,
    "next_buildable_selector_present": False,
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bounded_str(value: Any, max_len: int = MAX_EVIDENCE_VALUE_LEN) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _make_evidence(
    *,
    kind: str,
    value: str,
    decision: str,
    reason: str,
    source: str,
) -> dict[str, Any]:
    """Construct a bounded-scalar evidence record."""
    return {
        "kind": kind,
        "value": _bounded_str(value, MAX_EVIDENCE_VALUE_LEN),
        "decision": decision,
        "reason": _bounded_str(reason, MAX_REASON_LEN),
        "source": source,
    }


# ---------------------------------------------------------------------------
# Evidence builders — one per evidence kind
# ---------------------------------------------------------------------------


def _classify_path(
    path: str, *, risk_class: str
) -> tuple[str, str, str]:
    """Call the canonical classifier for one path. Returns
    ``(decision, reason, target_path_category)``."""
    decision = ea.classify(
        action_type="file_edit",
        target_path=path,
        risk_class=risk_class,
    )
    return decision.decision, decision.reason, decision.target_path_category


def _build_expected_file_evidence(
    unit: dict[str, Any], *, risk_class: str
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for path in unit.get("expected_files", []) or []:
        decision, reason, _ = _classify_path(path, risk_class=risk_class)
        evidence.append(
            _make_evidence(
                kind="expected_file_classifier",
                value=path,
                decision=decision,
                reason=reason,
                source=_SOURCE_CLASSIFIER,
            )
        )
    return evidence


def _build_forbidden_file_evidence(
    unit: dict[str, Any], *, risk_class: str
) -> list[dict[str, Any]]:
    """Record the classifier verdict for every forbidden_files entry.
    These records are informational — they do not contribute to the
    unit's aggregate (see ``_AGGREGATING_EVIDENCE_KINDS``). They
    exist so operators can audit that forbidden surfaces are indeed
    being denied by the canonical classifier."""
    evidence: list[dict[str, Any]] = []
    for path in unit.get("forbidden_files", []) or []:
        decision, reason, _ = _classify_path(path, risk_class=risk_class)
        evidence.append(
            _make_evidence(
                kind="forbidden_file_classifier",
                value=path,
                decision=decision,
                reason=reason,
                source=_SOURCE_CLASSIFIER,
            )
        )
    return evidence


_TARGET_LAYER_DECISIONS: Final[dict[str, tuple[str, str]]] = {
    "live": (_PERMANENTLY_DENIED, "live_runtime_activation_not_authorised"),
    "paper": (_NEEDS_HUMAN, "paper_runtime_activation_not_authorised"),
    "shadow": (_NEEDS_HUMAN, "shadow_runtime_activation_not_authorised"),
}


def _build_target_layer_evidence(
    unit: dict[str, Any],
) -> list[dict[str, Any]]:
    target_layer = unit.get("target_layer")
    if not isinstance(target_layer, str):
        return [
            _make_evidence(
                kind="target_layer",
                value="(missing)",
                decision=_NEEDS_HUMAN,
                reason="fail_closed_unknown_target_layer",
                source=_SOURCE_A20C,
            )
        ]
    if target_layer not in rtu.TARGET_LAYER:
        return [
            _make_evidence(
                kind="target_layer",
                value=target_layer,
                decision=_NEEDS_HUMAN,
                reason="fail_closed_unknown_target_layer",
                source=_SOURCE_A20C,
            )
        ]
    rule = _TARGET_LAYER_DECISIONS.get(target_layer)
    if rule is not None:
        decision, reason = rule
        return [
            _make_evidence(
                kind="target_layer",
                value=target_layer,
                decision=decision,
                reason=reason,
                source=_SOURCE_A20C,
            )
        ]
    return [
        _make_evidence(
            kind="target_layer",
            value=target_layer,
            decision=_AUTO_ALLOWED,
            reason="non_path_evidence_baseline",
            source=_SOURCE_A20C,
        )
    ]


def _build_risk_class_evidence(
    unit: dict[str, Any], *, risk_class: str
) -> list[dict[str, Any]]:
    raw = unit.get("risk_class")
    if raw not in ea.RISK_CLASSES:
        return [
            _make_evidence(
                kind="risk_class",
                value=str(raw),
                decision=_NEEDS_HUMAN,
                reason="fail_closed_unknown_risk_class",
                source=_SOURCE_A20C,
            )
        ]
    if raw == ea.RISK_UNKNOWN:
        return [
            _make_evidence(
                kind="risk_class",
                value=raw,
                decision=_NEEDS_HUMAN,
                reason="unknown_risk_or_target_fail_safe",
                source=_SOURCE_A20C,
            )
        ]
    return [
        _make_evidence(
            kind="risk_class",
            value=raw,
            decision=_AUTO_ALLOWED,
            reason="non_path_evidence_baseline",
            source=_SOURCE_A20C,
        )
    ]


def _build_operator_gate_evidence(
    unit: dict[str, Any],
) -> list[dict[str, Any]]:
    gate = unit.get("operator_gate")
    if not isinstance(gate, str) or gate not in rtu.OPERATOR_GATE:
        return [
            _make_evidence(
                kind="operator_gate",
                value=str(gate),
                decision=_NEEDS_HUMAN,
                reason="fail_closed_unknown_operator_gate",
                source=_SOURCE_A20C,
            )
        ]
    if gate == "operator_go_required":
        return [
            _make_evidence(
                kind="operator_gate",
                value=gate,
                decision=_NEEDS_HUMAN,
                reason="operator_gate_required",
                source=_SOURCE_A20C,
            )
        ]
    if gate == "governance_bootstrap_pr_required":
        return [
            _make_evidence(
                kind="operator_gate",
                value=gate,
                decision=_NEEDS_HUMAN,
                reason="governance_bootstrap_pr_required",
                source=_SOURCE_A20C,
            )
        ]
    # gate == "none"
    return [
        _make_evidence(
            kind="operator_gate",
            value=gate,
            decision=_AUTO_ALLOWED,
            reason="non_path_evidence_baseline",
            source=_SOURCE_A20C,
        )
    ]


_HINT_TO_DECISION: Final[dict[str, str]] = {
    "AUTO_ALLOWED_CANDIDATE": _AUTO_ALLOWED,
    "NEEDS_HUMAN_CANDIDATE": _NEEDS_HUMAN,
    "PERMANENTLY_DENIED_SURFACE": _PERMANENTLY_DENIED,
}


def _build_authority_hint_evidence(
    unit: dict[str, Any],
) -> list[dict[str, Any]]:
    hint = unit.get("authority_hint")
    if not isinstance(hint, str) or hint not in rtu.AUTHORITY_HINT:
        return [
            _make_evidence(
                kind="authority_hint",
                value=str(hint),
                decision=_NEEDS_HUMAN,
                reason="fail_closed_unknown_authority_hint",
                source=_SOURCE_A20C,
            )
        ]
    decision = _HINT_TO_DECISION[hint]
    if decision == _AUTO_ALLOWED:
        reason = "non_path_evidence_baseline"
    elif decision == _NEEDS_HUMAN:
        reason = "operator_gate_required"
    else:
        reason = "denied_live_path_modification"
    return [
        _make_evidence(
            kind="authority_hint",
            value=hint,
            decision=decision,
            reason=reason,
            source=_SOURCE_A20C,
        )
    ]


_UNIT_KIND_REASONS: Final[dict[str, tuple[str, str]]] = {
    "research_module": (_NEEDS_HUMAN, "research_module_requires_human_review"),
    "diagnostic_primitive": (
        _NEEDS_HUMAN,
        "diagnostic_primitive_requires_human_review",
    ),
    "external_intelligence_source": (
        _NEEDS_HUMAN,
        "external_intelligence_source_requires_human_review",
    ),
}


def _build_unit_kind_evidence(unit: dict[str, Any]) -> list[dict[str, Any]]:
    kind = unit.get("unit_kind")
    if not isinstance(kind, str) or kind not in rtu.UNIT_KIND:
        return [
            _make_evidence(
                kind="unit_kind",
                value=str(kind),
                decision=_NEEDS_HUMAN,
                reason="fail_closed_unknown_unit_kind",
                source=_SOURCE_A20C,
            )
        ]
    rule = _UNIT_KIND_REASONS.get(kind)
    if rule is not None:
        decision, reason = rule
        return [
            _make_evidence(
                kind="unit_kind",
                value=kind,
                decision=decision,
                reason=reason,
                source=_SOURCE_A20C,
            )
        ]
    return [
        _make_evidence(
            kind="unit_kind",
            value=kind,
            decision=_AUTO_ALLOWED,
            reason="non_path_evidence_baseline",
            source=_SOURCE_A20C,
        )
    ]


def _build_stop_conditions_evidence(
    unit: dict[str, Any],
) -> list[dict[str, Any]]:
    """Record the unit's stop_conditions as bounded-scalar
    informational evidence. Stop conditions describe what the future
    PR must NOT do; they are recorded for transparency but do not
    elevate aggregation (this kind is in
    :data:`_INFORMATIONAL_EVIDENCE_KINDS`)."""
    out: list[dict[str, Any]] = []
    for sc in unit.get("stop_conditions", []) or []:
        out.append(
            _make_evidence(
                kind="stop_conditions",
                value=sc,
                decision=_AUTO_ALLOWED,
                reason="stop_conditions_informational_only",
                source=_SOURCE_A20C,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(evidence: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Reduce evidence to ``(final_class, deny_reasons)`` via
    max-severity over the aggregating-kinds subset. Fail-closed:
    if there is no aggregating evidence at all (defence in depth),
    return ``NEEDS_HUMAN`` + ``["fail_closed_unknown_evidence"]``."""
    aggregating = [
        e for e in evidence if e["kind"] in _AGGREGATING_EVIDENCE_KINDS
    ]
    if not aggregating:
        return _NEEDS_HUMAN, ["fail_closed_unknown_evidence"]

    # First-match wins per severity tier — preserves the first
    # contributing reason for transparency.
    for e in aggregating:
        if e["decision"] == _PERMANENTLY_DENIED:
            deny_reasons = [
                ev["reason"]
                for ev in aggregating
                if ev["decision"] == _PERMANENTLY_DENIED
            ]
            return _PERMANENTLY_DENIED, deny_reasons[:MAX_DENY_REASONS]
    for e in aggregating:
        if e["decision"] == _NEEDS_HUMAN:
            return _NEEDS_HUMAN, []
    return _AUTO_ALLOWED, []


def _decide_for_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Build one ``UnitAuthorityDecision`` from one A20b unit."""
    raw_risk = unit.get("risk_class")
    # Normalise risk for the classifier call only. The risk-class
    # evidence builder records the *raw* value so fail-closed
    # detection is auditable.
    risk_class_for_classifier = (
        raw_risk if raw_risk in ea.RISK_CLASSES else ea.RISK_UNKNOWN
    )

    evidence: list[dict[str, Any]] = []
    evidence.extend(
        _build_expected_file_evidence(unit, risk_class=risk_class_for_classifier)
    )
    evidence.extend(
        _build_forbidden_file_evidence(unit, risk_class=risk_class_for_classifier)
    )
    evidence.extend(_build_target_layer_evidence(unit))
    evidence.extend(
        _build_risk_class_evidence(unit, risk_class=risk_class_for_classifier)
    )
    evidence.extend(_build_operator_gate_evidence(unit))
    evidence.extend(_build_authority_hint_evidence(unit))
    evidence.extend(_build_unit_kind_evidence(unit))
    evidence.extend(_build_stop_conditions_evidence(unit))

    final_class, deny_reasons = _aggregate(evidence)

    classifier_used = any(
        e["source"] == _SOURCE_CLASSIFIER for e in evidence
    )
    fail_closed = any(
        e["reason"].startswith("fail_closed_") for e in evidence
    )

    return {
        "implementation_unit_id": unit["id"],
        "roadmap_task_id": unit["roadmap_task_id"],
        "phase": unit["phase"],
        "final_authority_class": final_class,
        "max_severity": _SEVERITY[final_class],
        "evidence": evidence,
        "requires_operator_go": final_class == _NEEDS_HUMAN,
        "permanently_denied": final_class == _PERMANENTLY_DENIED,
        "deny_reasons": deny_reasons,
        "classifier_used": classifier_used,
        "fail_closed": fail_closed,
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic Roadmap-unit-authority projection."""
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    units_snapshot = rtu.collect_snapshot(generated_at_utc=ts)
    decisions = [
        _decide_for_unit(u) for u in units_snapshot["implementation_units"]
    ]
    decisions.sort(key=lambda r: (r["phase"], r["implementation_unit_id"]))

    if not decisions:
        status = "no_units"
    else:
        status = "ok"

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "projection_status": status,
        "source_units_module_version": units_snapshot["module_version"],
        "source_units_schema_version": units_snapshot["schema_version"],
        "classifier_module_version": ea.MODULE_VERSION,
        "classifier_schema_version": ea.SCHEMA_VERSION,
        "vocabularies": {
            "authority_class": list(AUTHORITY_CLASS),
            "authority_reason": list(AUTHORITY_REASON),
            "authority_evidence_kind": list(AUTHORITY_EVIDENCE_KIND),
            "authority_projection_status": list(AUTHORITY_PROJECTION_STATUS),
            "aggregating_evidence_kinds": sorted(_AGGREGATING_EVIDENCE_KINDS),
            "informational_evidence_kinds": sorted(
                _INFORMATIONAL_EVIDENCE_KINDS
            ),
        },
        "authority_decisions": decisions,
        "authority_invariants": dict(_BASE_AUTHORITY_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as sorted-key indented JSON to ``path``,
    atomically, refusing any path outside
    ``logs/roadmap_unit_authority/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "roadmap_unit_authority._atomic_write_json refuses "
            f"non-authority-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".roadmap_unit_authority.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# Status renderer
# ---------------------------------------------------------------------------


def _render_status(snapshot: dict[str, Any]) -> str:
    decisions = snapshot["authority_decisions"]
    inv = snapshot["authority_invariants"]
    by_class: dict[str, int] = {c: 0 for c in AUTHORITY_CLASS}
    fail_closed_count = 0
    classifier_used_count = 0
    for d in decisions:
        by_class[d["final_authority_class"]] += 1
        if d["fail_closed"]:
            fail_closed_count += 1
        if d["classifier_used"]:
            classifier_used_count += 1
    lines = [
        f"roadmap_unit_authority {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"authority_decisions={len(decisions)} status={snapshot['projection_status']}",
        (
            "step5_implementation_allowed="
            f"{snapshot['step5_implementation_allowed']} "
            f"step5_enabled_substage={snapshot['step5_enabled_substage']}"
        ),
        (
            "calls_execution_authority_classifier="
            f"{inv['calls_execution_authority_classifier']} "
            "final_authority_classified="
            f"{inv['final_authority_classified']}"
        ),
        (
            "no_runtime_trading_authority="
            f"{inv['no_runtime_trading_authority']} "
            f"no_step5_runtime={inv['no_step5_runtime']} "
            f"no_level6={inv['no_level6']} "
            "no_production_merge_authority="
            f"{inv['no_production_merge_authority']}"
        ),
        (
            "aac_visibility_present="
            f"{inv['aac_visibility_present']} "
            "next_buildable_selector_present="
            f"{inv['next_buildable_selector_present']}"
        ),
        f"classifier_used_count={classifier_used_count}",
        f"fail_closed_count={fail_closed_count}",
        f"by_final_authority_class={dict(sorted(by_class.items()))}",
    ]
    for d in decisions:
        lines.append(
            f"  unit {d['implementation_unit_id']} "
            f"phase={d['phase']} "
            f"final={d['final_authority_class']} "
            f"requires_operator_go={d['requires_operator_go']} "
            f"permanently_denied={d['permanently_denied']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.roadmap_unit_authority",
        description=(
            "A20c Roadmap Unit Authority Classifier Integration. "
            "Read-only deterministic projection that classifies every "
            "A20b implementation unit via the canonical "
            "reporting.execution_authority classifier plus closed-vocab "
            "rules for non-path evidence kinds. No second source of "
            "truth for path authority. Step 5 implementation remains "
            "BLOCKED."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout output (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/roadmap_unit_authority/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--status",
        action="store_true",
        help=(
            "Render a compact human-readable status summary to stdout "
            "and exit. Does not write any artefact."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snap = collect_snapshot()
    if args.status:
        sys.stdout.write(_render_status(snap))
        return 0
    indent = args.indent if args.indent and args.indent > 0 else None
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
