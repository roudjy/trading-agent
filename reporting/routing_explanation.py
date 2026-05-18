"""v3.15.16 Intelligent Routing Layer — read-only routing-decision
explanation reporter.

Implements the queue-driven Roadmap v6 implementation unit selected
by A20e after PR #251 advanced the queue status:

* unit id: ``u_v3_15_16_routing_explanation_reporter_001``
* phase:   ``v3.15.16`` — Intelligent Routing Layer
* authority: ``AUTO_ALLOWED`` at LOW risk (per A20c verdict)
* prerequisite: ``u_v3_15_16_diagnostic_routing_signals_schema_001``
  (merged via PR #250 / SHA fcb1abb; queue status advanced via
  PR #251 / SHA dcbed07)

This module is **explanation / reporting only**. It consumes the
read-only ``RoutingSignalProjection`` emitted by
:mod:`reporting.intelligent_routing_diagnostic_signals` (PR #250)
and produces operator-readable explanations for why each diagnostic
routing signal would support, suppress, or require confirmation
for research exploration.

The module does NOT make actual routing decisions, does NOT mutate
any campaign queue, does NOT enqueue campaigns, does NOT change
research runtime behaviour, does NOT generate strategies, does NOT
trade. The closed-vocabulary mapping from signal direction to
explanation effect is hand-encoded as Python literals — no LLM,
no fuzzy parsing, no hidden scoring.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.intelligent_routing_diagnostic_signals``
  (read-only) only.
* No subprocess, no network, no ``gh``, no ``git``, no GitHub
  API.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_agent_activity_timeline``,
  ``reporting.execution_authority``, or any of the A20 pipeline
  modules.
* No LLM, no external API, no fuzzy parsing, no runtime parsing
  of canonical roadmap documents.
* Atomic write only under ``logs/routing_explanation/``.
* Deterministic output: same input + injected
  ``generated_at_utc`` → byte-identical artefact.
* Every emitted explanation carries ``read_only=True`` and
  ``mutation_allowed=False`` markers.
* No actual routing decision; no campaign queue mutation; no
  strategy generation (pinned by ``projection_invariants``).
* Diagnostics do not trade. External data is not alpha.

CLI::

    python -m reporting.routing_explanation
    python -m reporting.routing_explanation --no-write
    python -m reporting.routing_explanation --status
    python -m reporting.routing_explanation --indent 2
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

from reporting import intelligent_routing_diagnostic_signals as rsd

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.routing_explanation.0"
REPORT_KIND: Final[str] = "routing_explanation"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed explanation-status vocabulary. Mirrors the routing-signal
#: directions plus an ``informational`` fallback for any explanation
#: that does not map to a single direction (currently none — every
#: signal direction has a matching status, pinned by tests).
ROUTING_EXPLANATION_STATUS: Final[tuple[str, ...]] = (
    "advisory_prioritize",
    "advisory_deprioritize",
    "advisory_suppress",
    "advisory_require_confirmation",
    "advisory_neutral",
    "informational",
)

#: Closed reason-kind vocabulary. Each explanation emits at least
#: one reason; every reason's ``kind`` belongs to this enum.
ROUTING_EXPLANATION_REASON_KIND: Final[tuple[str, ...]] = (
    "direction_advice",
    "expected_information_gain",
    "dead_zone_risk",
    "orthogonality",
    "public_data_quality",
    "confirmation_requirement",
    "missing_input_fallback",
)

#: Closed effect vocabulary. Every reason and every aggregated
#: explanation effect belongs to this enum. Never a buy/sell verb.
ROUTING_EXPLANATION_EFFECT: Final[tuple[str, ...]] = (
    "supports_exploration",
    "suppresses_exploration",
    "requires_confirmation",
    "lowers_priority",
    "elevates_evidence_requirement",
    "neutral",
)

#: Closed target vocabulary. Verbatim re-export of the upstream
#: ``ROUTING_SIGNAL_TARGET_LAYER`` so explanations and signals
#: share one target-layer enum.
ROUTING_EXPLANATION_TARGET: Final[tuple[str, ...]] = (
    rsd.ROUTING_SIGNAL_TARGET_LAYER
)

#: Closed source vocabulary. Either the upstream signal module
#: (the per-signal direction-advice and missing-input-fallback
#: reasons) or this module (the family-specific reason whose
#: mapping rule lives here).
ROUTING_EXPLANATION_SOURCE: Final[tuple[str, ...]] = (
    "reporting.intelligent_routing_diagnostic_signals",
    "reporting.routing_explanation",
    "logs/intelligent_routing_diagnostic_signals/latest.json",
)


# ---------------------------------------------------------------------------
# Closed deterministic mappings
# ---------------------------------------------------------------------------

#: Direction (from upstream signal) → explanation status. Closed,
#: exhaustive over ``ROUTING_SIGNAL_DIRECTION``.
_DIRECTION_TO_STATUS: Final[dict[str, str]] = {
    "prioritize": "advisory_prioritize",
    "deprioritize": "advisory_deprioritize",
    "suppress": "advisory_suppress",
    "require_confirmation": "advisory_require_confirmation",
    "neutral": "advisory_neutral",
}

#: Direction → direction-advice effect. Closed.
_DIRECTION_TO_EFFECT: Final[dict[str, str]] = {
    "prioritize": "supports_exploration",
    "deprioritize": "lowers_priority",
    "suppress": "suppresses_exploration",
    "require_confirmation": "requires_confirmation",
    "neutral": "neutral",
}

#: Direction → aggregate-boolean tuple
#: ``(supports_exploration, suppresses_exploration, requires_confirmation)``.
#: Closed.
_DIRECTION_TO_AGGREGATE: Final[dict[str, tuple[bool, bool, bool]]] = {
    # supports, suppresses, requires_confirmation
    "prioritize": (True, False, False),
    "deprioritize": (False, False, True),
    "suppress": (False, True, False),
    "require_confirmation": (False, False, True),
    "neutral": (False, False, False),
}

#: Family → (family-specific reason kind, family-specific reason
#: effect). Closed, exhaustive over
#: ``ROUTING_SIGNAL_FAMILY``. The kind / effect both come from
#: closed vocabularies above; no fuzzy parsing.
_FAMILY_TO_REASON: Final[dict[str, tuple[str, str]]] = {
    "entropy": ("expected_information_gain", "lowers_priority"),
    "tail": ("confirmation_requirement", "elevates_evidence_requirement"),
    "criticality": ("dead_zone_risk", "lowers_priority"),
    "network": ("orthogonality", "supports_exploration"),
    "quorum": ("confirmation_requirement", "elevates_evidence_requirement"),
    "external_intelligence": (
        "public_data_quality",
        "elevates_evidence_requirement",
    ),
    "dead_zone": ("dead_zone_risk", "lowers_priority"),
    "null_model": ("expected_information_gain", "lowers_priority"),
    "barrier": ("confirmation_requirement", "elevates_evidence_requirement"),
    "resonance": (
        "confirmation_requirement",
        "elevates_evidence_requirement",
    ),
    "adversarial": (
        "confirmation_requirement",
        "elevates_evidence_requirement",
    ),
    "seismic": ("dead_zone_risk", "lowers_priority"),
    "turbulence": ("dead_zone_risk", "lowers_priority"),
    "market_language": ("expected_information_gain", "lowers_priority"),
}

#: Family → which upstream signal effect string is copied into the
#: family-specific reason's ``reason`` field. Closed.
_FAMILY_TO_REASON_FIELD: Final[dict[str, str]] = {
    "entropy": "expected_information_gain_effect",
    "tail": "confirmation_requirement_effect",
    "criticality": "dead_zone_risk_effect",
    "network": "orthogonality_effect",
    "quorum": "confirmation_requirement_effect",
    "external_intelligence": "public_data_quality_effect",
    "dead_zone": "dead_zone_risk_effect",
    "null_model": "expected_information_gain_effect",
    "barrier": "confirmation_requirement_effect",
    "resonance": "confirmation_requirement_effect",
    "adversarial": "confirmation_requirement_effect",
    "seismic": "dead_zone_risk_effect",
    "turbulence": "dead_zone_risk_effect",
    "market_language": "expected_information_gain_effect",
}


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: Per-reason schema.
ROUTING_EXPLANATION_REASON_FIELDS: Final[tuple[str, ...]] = (
    "kind",
    "signal_id",
    "signal_family",
    "reason",
    "effect",
    "source",
)

#: Per-explanation schema.
ROUTING_EXPLANATION_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "signal_id",
    "signal_family",
    "title",
    "summary",
    "status",
    "target",
    "reasons",
    "supports_exploration",
    "suppresses_exploration",
    "requires_confirmation",
    "read_only",
    "mutation_allowed",
)

#: Top-level projection schema.
ROUTING_EXPLANATION_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "source_signal_schema_version",
    "explanations",
    "projection_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_TITLE_LEN: Final[int] = 200
MAX_SUMMARY_LEN: Final[int] = 600
MAX_REASON_LEN: Final[int] = 240
MAX_REASONS_PER_EXPLANATION: Final[int] = 8


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "routing_explanation"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/routing_explanation/latest.json"

_WRITE_PREFIX: Final[str] = "logs/routing_explanation/"


# ---------------------------------------------------------------------------
# Projection invariants emitted on every snapshot
# ---------------------------------------------------------------------------

_BASE_PROJECTION_INVARIANTS: Final[dict[str, bool]] = {
    # Doctrinal anchors carried forward from the upstream schema.
    "diagnostics_do_not_trade": True,
    "external_data_is_not_alpha": True,
    "read_only": True,
    "mutation_allowed": False,
    # A20 authority chain pins.
    "no_runtime_trading_authority": True,
    "no_campaign_queue_mutation": True,
    "no_actual_routing_decision": True,
    "no_strategy_generation": True,
    "no_routing_mutation": True,
    "no_research_runtime_change": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "step5_implementation_allowed": False,
    # Operational pins.
    "no_branch_creation": True,
    "no_pr_creation": True,
    "no_merge_or_deploy": True,
    "no_mutation_routes": True,
    "no_approval_buttons": True,
    "writes_only_routing_explanation_log": True,
    "fuzzy_parsing": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
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


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


# ---------------------------------------------------------------------------
# Reason builders
# ---------------------------------------------------------------------------


def _direction_advice_reason(signal: dict[str, Any]) -> dict[str, Any]:
    direction = signal.get("direction", "neutral")
    if direction not in _DIRECTION_TO_EFFECT:
        direction = "neutral"
    effect = _DIRECTION_TO_EFFECT[direction]
    return {
        "kind": "direction_advice",
        "signal_id": signal["id"],
        "signal_family": signal["family"],
        "reason": _bounded_str(
            f"signal direction is {direction}",
            MAX_REASON_LEN,
        ),
        "effect": effect,
        "source": "reporting.intelligent_routing_diagnostic_signals",
    }


def _family_specific_reason(signal: dict[str, Any]) -> dict[str, Any]:
    family = signal["family"]
    if family not in _FAMILY_TO_REASON:
        # Fail-closed: unknown family yields a missing-input-style
        # reason rather than guessing. Closed-vocab inputs make
        # this branch unreachable in practice; tests pin every
        # family from the upstream seed against the mapping.
        return {
            "kind": "missing_input_fallback",
            "signal_id": signal["id"],
            "signal_family": family,
            "reason": _bounded_str(
                "family-specific reason mapping unavailable",
                MAX_REASON_LEN,
            ),
            "effect": "neutral",
            "source": "reporting.routing_explanation",
        }
    kind, effect = _FAMILY_TO_REASON[family]
    field_name = _FAMILY_TO_REASON_FIELD[family]
    reason_text = signal.get(field_name, "")
    return {
        "kind": kind,
        "signal_id": signal["id"],
        "signal_family": family,
        "reason": _bounded_str(reason_text, MAX_REASON_LEN),
        "effect": effect,
        "source": "reporting.routing_explanation",
    }


def _missing_input_reason(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "missing_input_fallback",
        "signal_id": signal["id"],
        "signal_family": signal["family"],
        "reason": _bounded_str(
            signal.get("missing_input_behavior", ""),
            MAX_REASON_LEN,
        ),
        "effect": "neutral",
        "source": "reporting.intelligent_routing_diagnostic_signals",
    }


# ---------------------------------------------------------------------------
# Explanation construction
# ---------------------------------------------------------------------------


def _explanation_from_signal(signal: dict[str, Any]) -> dict[str, Any]:
    direction = signal.get("direction", "neutral")
    if direction not in _DIRECTION_TO_STATUS:
        direction = "neutral"

    supports, suppresses, requires_confirmation = (
        _DIRECTION_TO_AGGREGATE.get(direction, (False, False, False))
    )
    status = _DIRECTION_TO_STATUS.get(direction, "informational")

    reasons = [
        _direction_advice_reason(signal),
        _family_specific_reason(signal),
        _missing_input_reason(signal),
    ]
    # Cap defensively (never exceeded by today's seed).
    reasons = reasons[:MAX_REASONS_PER_EXPLANATION]

    family = signal["family"]
    name = signal.get("name", signal["id"])
    target_layer = signal["target_layer"]

    title = _bounded_str(
        f"Routing explanation for {family} signal ({signal['id']})",
        MAX_TITLE_LEN,
    )
    summary = _bounded_str(
        (
            f"Routing-signal family={family} advises status={status} for the "
            f"{target_layer} layer. The signal {name.lower()}. This row is "
            "read-only / mutation_allowed=false; it makes no actual routing "
            "decision."
        ),
        MAX_SUMMARY_LEN,
    )

    return {
        "id": f"re_{signal['id']}",
        "signal_id": signal["id"],
        "signal_family": family,
        "title": title,
        "summary": summary,
        "status": status,
        "target": target_layer,
        "reasons": reasons,
        "supports_exploration": supports,
        "suppresses_exploration": suppresses,
        "requires_confirmation": requires_confirmation,
        "read_only": True,
        "mutation_allowed": False,
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic routing-explanation projection.

    Reads the upstream signal schema via the in-process
    ``intelligent_routing_diagnostic_signals.collect_snapshot()``.
    Never reads from disk; never mutates upstream state.
    """
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    upstream = rsd.collect_snapshot(generated_at_utc=ts)
    signals = upstream.get("signals") or []
    if not isinstance(signals, list):
        signals = []

    explanations: list[dict[str, Any]] = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        if "id" not in s or not isinstance(s["id"], str) or not s["id"]:
            continue
        explanations.append(_explanation_from_signal(s))

    # Deterministic ordering: signal_id ascending.
    explanations.sort(key=lambda e: e["signal_id"])

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "source_signal_schema_version": upstream.get("schema_version", ""),
        "source_signal_module_version": upstream.get("module_version", ""),
        "vocabularies": {
            "routing_explanation_status": list(ROUTING_EXPLANATION_STATUS),
            "routing_explanation_reason_kind": list(
                ROUTING_EXPLANATION_REASON_KIND
            ),
            "routing_explanation_effect": list(ROUTING_EXPLANATION_EFFECT),
            "routing_explanation_target": list(ROUTING_EXPLANATION_TARGET),
            "routing_explanation_source": list(ROUTING_EXPLANATION_SOURCE),
        },
        "explanations": explanations,
        "projection_invariants": dict(_BASE_PROJECTION_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write ``payload`` as sorted-key indented JSON.
    Refuses any path outside ``logs/routing_explanation/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "routing_explanation._atomic_write_json refuses "
            f"non-explanation-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".routing_explanation.",
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
    explanations = snapshot["explanations"]
    inv = snapshot["projection_invariants"]
    by_status: dict[str, int] = {s: 0 for s in ROUTING_EXPLANATION_STATUS}
    by_effect_supports = 0
    by_effect_suppresses = 0
    by_effect_requires_confirmation = 0
    for e in explanations:
        if e["status"] in by_status:
            by_status[e["status"]] += 1
        by_effect_supports += int(bool(e["supports_exploration"]))
        by_effect_suppresses += int(bool(e["suppresses_exploration"]))
        by_effect_requires_confirmation += int(
            bool(e["requires_confirmation"])
        )
    lines = [
        f"routing_explanation {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"explanations={len(explanations)}",
        (
            "step5_implementation_allowed="
            f"{snapshot['step5_implementation_allowed']} "
            f"step5_enabled_substage={snapshot['step5_enabled_substage']}"
        ),
        (
            "diagnostics_do_not_trade="
            f"{inv['diagnostics_do_not_trade']} "
            "external_data_is_not_alpha="
            f"{inv['external_data_is_not_alpha']}"
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
            "no_campaign_queue_mutation="
            f"{inv['no_campaign_queue_mutation']} "
            "no_actual_routing_decision="
            f"{inv['no_actual_routing_decision']} "
            "no_strategy_generation="
            f"{inv['no_strategy_generation']}"
        ),
        (
            "read_only="
            f"{inv['read_only']} "
            "mutation_allowed="
            f"{inv['mutation_allowed']}"
        ),
        f"by_status={dict(sorted(by_status.items()))}",
        (
            f"supports_exploration={by_effect_supports} "
            f"suppresses_exploration={by_effect_suppresses} "
            f"requires_confirmation={by_effect_requires_confirmation}"
        ),
    ]
    for e in explanations:
        lines.append(
            f"  expl {e['id']} signal={e['signal_id']} "
            f"family={e['signal_family']} target={e['target']} "
            f"status={e['status']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.routing_explanation",
        description=(
            "v3.15.16 Intelligent Routing Layer — read-only routing-"
            "decision explanation reporter. Consumes the diagnostic-"
            "aware routing-signals schema and emits operator-readable "
            "explanations. Explanation only; no actual routing "
            "decision, no campaign queue mutation, no strategy "
            "generation, no trading behaviour. Step 5 implementation "
            "remains BLOCKED."
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
            "Do not persist logs/routing_explanation/latest.json "
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
