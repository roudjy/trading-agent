from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_hypothesis_generation as a20
from packages.qre_research.generated_strategy_paths import (
    REPO_ROOT,
    repo_relative,
    validate_write_target,
)
from research import synthesis_gate as sg


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-027.1"
MAX_TUNABLE_PARAMETERS: Final[int] = 3
ALLOWED_PRIMITIVES: Final[dict[str, tuple[str, ...]]] = {
    "trend": (
        "trend_anchor",
        "trend_anchor_delta",
        "normalized_trend_move",
    ),
    "cross_sectional": ("cross_sectional_rank",),
}
DEFAULT_EXIT_EXPRESSION: Final[str] = "neutral_research_exit"
BLUEPRINTS_DIR: Final[Path] = Path("generated_research/strategies/blueprints")
CANDIDATES_DIR: Final[Path] = Path("generated_research/strategies/candidates")
VALIDATION_DIR: Final[Path] = Path("generated_research/strategies/validation")
PROPOSALS_DIR: Final[Path] = Path("generated_research/strategies/proposals")
READINESS_PATH: Final[Path] = Path(
    "generated_research/strategies/readiness/generated_hypothesis_synthesis_readiness.v1.json"
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".ade_qre_027.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _candidate_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    compiled = a20.compile_candidate_theses(repo_root=repo_root)
    return {
        str(row.get("thesis_id") or ""): row
        for row in compiled.get("rows", [])
        if str(row.get("thesis_id") or "")
    }


def _generated_hypothesis_rows(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("thesis_id") or ""): row
        for row in _read_rows(
            repo_root
            / "generated_research"
            / "hypotheses"
            / "registry"
            / "generated_thesis_registry.v1.json"
        )
        if str(row.get("thesis_id") or "")
    }


def _blueprint_paths(repo_root: Path, blueprint_id: str) -> dict[str, Path]:
    return {
        "blueprint": repo_root / BLUEPRINTS_DIR / f"{blueprint_id}.json",
        "candidate": repo_root / CANDIDATES_DIR / f"{blueprint_id}.json",
        "validation": repo_root / VALIDATION_DIR / f"{blueprint_id}.json",
        "proposal": repo_root / PROPOSALS_DIR / f"{blueprint_id}.json",
    }


def readiness_artifact_path() -> Path:
    return READINESS_PATH


def materialize_synthesis_readiness(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
) -> dict[str, Any]:
    generated_artifacts, statuses = sg.load_generated_hypothesis_artifacts(root=repo_root)
    payload = sg.build_generated_hypothesis_synthesis_payload(
        generated_artifacts=generated_artifacts,
        artifact_status=statuses,
    )
    if write_outputs:
        _atomic_write(
            repo_root / readiness_artifact_path(),
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
    return payload


def _primitive_family(row: dict[str, Any]) -> str:
    behavior_family = str(row.get("behavior_family") or "").strip().lower()
    if behavior_family.startswith("cross_sectional"):
        return "cross_sectional"
    return "trend"


def _parameter_spec(primitive_family: str) -> dict[str, dict[str, Any]]:
    if primitive_family == "cross_sectional":
        return {
            "lookback_bars": {"type": "int", "min": 10, "max": 40, "default": 20},
            "entry_rank_threshold": {
                "type": "float",
                "min": 0.6,
                "max": 0.9,
                "default": 0.75,
            },
            "exit_rank_threshold": {
                "type": "float",
                "min": 0.3,
                "max": 0.6,
                "default": 0.5,
            },
        }
    return {
        "trend_anchor_window": {"type": "int", "min": 20, "max": 80, "default": 50},
        "entry_threshold": {"type": "float", "min": 0.5, "max": 1.5, "default": 0.75},
        "exit_threshold": {"type": "float", "min": 0.0, "max": 0.5, "default": 0.1},
    }


def build_strategy_blueprint(
    *,
    repo_root: Path = REPO_ROOT,
    hypothesis_id: str,
    readiness_payload: dict[str, Any],
) -> dict[str, Any]:
    generated_row = _generated_hypothesis_rows(repo_root).get(hypothesis_id, {})
    candidate_row = _candidate_index(repo_root).get(hypothesis_id, {})
    if not generated_row:
        raise ValueError(f"generated hypothesis not found: {hypothesis_id}")

    primitive_family = _primitive_family(generated_row)
    primitives = list(ALLOWED_PRIMITIVES[primitive_family])
    params = _parameter_spec(primitive_family)
    source_hypothesis_id = str(generated_row.get("source_hypothesis_id") or "")
    timeframes = [
        part
        for part in str(candidate_row.get("timeframe") or generated_row.get("timeframe") or "").split("|")
        if part
    ] or ["1h"]
    universes = list(candidate_row.get("universe") or candidate_row.get("universes") or [])
    if not universes:
        universe_value = str(candidate_row.get("asset_scope") or "repository_local_universe")
        universes = [universe_value]

    blueprint_basis = {
        "hypothesis_id": hypothesis_id,
        "source_hypothesis_id": source_hypothesis_id,
        "behavior_id": str(candidate_row.get("behavior_id") or generated_row.get("behavior_family") or ""),
        "mechanism_family": str(
            generated_row.get("mechanism_class")
            or candidate_row.get("expected_mechanism")
            or primitive_family
        ),
        "timeframes": timeframes,
        "universes": universes,
        "allowed_primitives": primitives,
        "parameter_spec": params,
        "expected_observables": list(candidate_row.get("entry_relevant_observations") or []),
        "falsification_criteria": list(candidate_row.get("falsification_criteria") or []),
    }
    blueprint_id = f"qsbp_{stable_digest(blueprint_basis)[:16]}"
    entry_expression = (
        "cross_sectional_rank_at_or_above(entry_rank_threshold)"
        if primitive_family == "cross_sectional"
        else "trend_anchor_delta_positive and normalized_trend_move_above(entry_threshold)"
    )
    exit_expression = (
        "cross_sectional_rank_at_or_below(exit_rank_threshold)"
        if primitive_family == "cross_sectional"
        else DEFAULT_EXIT_EXPRESSION
    )
    blueprint = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "blueprint_id": blueprint_id,
        "source_hypothesis_id": source_hypothesis_id,
        "hypothesis_id": hypothesis_id,
        "behavior_id": blueprint_basis["behavior_id"],
        "behavior_edge": primitive_family,
        "mechanism_family": blueprint_basis["mechanism_family"],
        "universe_constraints": universes,
        "timeframe_constraints": timeframes,
        "entry_signal_expression": entry_expression,
        "exit_signal_expression": exit_expression,
        "allowed_primitives": primitives,
        "parameter_definitions": params,
        "expected_observables": blueprint_basis["expected_observables"],
        "falsification_criteria": blueprint_basis["falsification_criteria"],
        "transaction_cost_assumptions": {"mode": "cost_class_visible_only"},
        "lookahead_constraints": {"lookahead_safe": True, "oos_conservation": True},
        "data_requirements": list(candidate_row.get("required_data") or []),
        "known_risks": list(candidate_row.get("known_risks") or ["empirical_evidence_incomplete"]),
        "provenance": {
            "readiness_artifact": repo_relative(repo_root / readiness_artifact_path()),
            "generated_hypothesis_registry": "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
            "source_hypothesis_id": source_hypothesis_id,
        },
        "synthesis_version": MODULE_VERSION,
    }
    blueprint["content_hash"] = stable_digest(blueprint)
    return blueprint


def validate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    params = dict(blueprint.get("parameter_definitions") or {})
    primitives = list(blueprint.get("allowed_primitives") or [])
    behavior_edge = str(blueprint.get("behavior_edge") or "")
    if not blueprint.get("hypothesis_id"):
        errors.append("missing_hypothesis_id")
    if len(params) > MAX_TUNABLE_PARAMETERS:
        errors.append("parameter_count_exceeds_bound")
    for primitive in primitives:
        if primitive not in ALLOWED_PRIMITIVES.get(behavior_edge, ()):
            errors.append(f"primitive_not_allowlisted:{primitive}")
    if not blueprint.get("entry_signal_expression"):
        errors.append("missing_entry_expression")
    if not blueprint.get("exit_signal_expression"):
        errors.append("missing_exit_expression")
    if blueprint.get("content_hash") != stable_digest(
        {key: value for key, value in blueprint.items() if key != "content_hash"}
    ):
        errors.append("content_hash_mismatch")
    return {
        "status": "PASSED" if not errors else "FAILED",
        "errors": errors,
        "parameter_count": len(params),
        "primitive_count": len(primitives),
    }


def build_research_only_candidate(
    *,
    blueprint: dict[str, Any],
    readiness_payload: dict[str, Any],
) -> dict[str, Any]:
    candidate_basis = {
        "blueprint_id": blueprint["blueprint_id"],
        "hypothesis_id": blueprint["hypothesis_id"],
        "content_hash": blueprint["content_hash"],
    }
    candidate_id = f"qsc_{stable_digest(candidate_basis)[:16]}"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "candidate_id": candidate_id,
        "blueprint_id": blueprint["blueprint_id"],
        "source_hypothesis_id": blueprint["source_hypothesis_id"],
        "hypothesis_id": blueprint["hypothesis_id"],
        "behavior_edge": blueprint["behavior_edge"],
        "allowed_primitives": list(blueprint["allowed_primitives"]),
        "parameter_definitions": dict(blueprint["parameter_definitions"]),
        "content_hash": stable_digest(candidate_basis),
        "enabled": False,
        "bundle_active": False,
        "active_discovery": False,
        "paper_ready": False,
        "shadow_ready": False,
        "live_eligible": False,
        "strategy_authority": False,
        "candidate_authority": False,
        "deployment_authority": False,
        "readiness_status": str(readiness_payload.get("readiness_status") or ""),
        "readiness_artifact": str(
            blueprint.get("provenance", {}).get("readiness_artifact") or ""
        ),
        "research_validation_status": "READY_FOR_CENTRAL_ORCHESTRATOR_RESEARCH_VALIDATION",
        "operator_gate": "strategy_registration_operator_approval_required",
    }


def validate_candidate(candidate: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if candidate.get("enabled") is not False:
        errors.append("enabled_must_remain_false")
    if candidate.get("paper_ready") is not False:
        errors.append("paper_ready_forbidden")
    if candidate.get("shadow_ready") is not False:
        errors.append("shadow_ready_forbidden")
    if candidate.get("live_eligible") is not False:
        errors.append("live_eligible_forbidden")
    if candidate.get("bundle_active") is not False:
        errors.append("bundle_active_forbidden")
    if candidate.get("active_discovery") is not False:
        errors.append("active_discovery_forbidden")
    if candidate.get("blueprint_id") != blueprint.get("blueprint_id"):
        errors.append("blueprint_lineage_mismatch")
    if len(dict(candidate.get("parameter_definitions") or {})) > MAX_TUNABLE_PARAMETERS:
        errors.append("candidate_parameter_count_exceeds_bound")
    return {"status": "PASSED" if not errors else "FAILED", "errors": errors}


def build_registration_proposal(
    *,
    blueprint: dict[str, Any],
    candidate: dict[str, Any],
    readiness_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "proposal_id": f"qsrp_{stable_digest({'candidate_id': candidate['candidate_id']})[:16]}",
        "candidate_id": candidate["candidate_id"],
        "source_hypothesis_id": candidate["source_hypothesis_id"],
        "blueprint_id": blueprint["blueprint_id"],
        "required_registry_diff": [],
        "required_strategy_file_diff": [],
        "authority_classification": "OPERATOR_GATED",
        "operator_gate": "strategy_registration_operator_approval_required",
        "default_disabled_invariants": {
            "enabled": False,
            "bundle_active": False,
            "active_discovery": False,
            "paper_ready": False,
            "shadow_ready": False,
            "live_eligible": False,
        },
        "evidence_basis": {
            "readiness_status": readiness_payload.get("readiness_status"),
            "criteria_passed": readiness_payload.get("criteria_passed"),
            "criteria_failed": readiness_payload.get("criteria_failed"),
            "missing_evidence": readiness_payload.get("missing_evidence"),
        },
        "rollback_plan": "delete generated_research/strategies artifacts for this blueprint and candidate",
    }


def run_bounded_strategy_synthesis(
    *,
    repo_root: Path = REPO_ROOT,
    hypothesis_id: str | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    readiness = materialize_synthesis_readiness(
        repo_root=repo_root,
        write_outputs=write_outputs,
    )
    selected_hypothesis_id = hypothesis_id or str(readiness.get("hypothesis_id") or "")
    result: dict[str, Any] = {
        "readiness_status": str(readiness.get("readiness_status") or "UNKNOWN"),
        "hypothesis_id": selected_hypothesis_id,
        "blueprint_created": False,
        "research_only_candidate_created": False,
        "promotion_proposal_created": False,
        "operator_gate": "strategy_registration_operator_approval_required",
        "artifact_paths": {
            "readiness": repo_relative(repo_root / readiness_artifact_path()),
        },
    }
    if readiness.get("readiness_status") != "ELIGIBLE":
        result["status"] = "BLOCKED_BY_READINESS"
        result["blocking_reasons"] = list(readiness.get("blocking_reasons") or [])
        result["recommended_next_actions"] = list(
            readiness.get("recommended_next_actions") or []
        )
        return result

    blueprint = build_strategy_blueprint(
        repo_root=repo_root,
        hypothesis_id=selected_hypothesis_id,
        readiness_payload=readiness,
    )
    blueprint_validation = validate_blueprint(blueprint)
    if blueprint_validation["status"] != "PASSED":
        result["status"] = "BLUEPRINT_VALIDATION_FAILED"
        result["blueprint_validation"] = blueprint_validation
        return result

    candidate = build_research_only_candidate(
        blueprint=blueprint,
        readiness_payload=readiness,
    )
    candidate_validation = validate_candidate(candidate, blueprint)
    if candidate_validation["status"] != "PASSED":
        result["status"] = "CANDIDATE_VALIDATION_FAILED"
        result["candidate_validation"] = candidate_validation
        return result

    proposal = build_registration_proposal(
        blueprint=blueprint,
        candidate=candidate,
        readiness_payload=readiness,
    )
    paths = _blueprint_paths(repo_root, blueprint["blueprint_id"])
    if write_outputs:
        _atomic_write(paths["blueprint"], json.dumps(blueprint, indent=2, sort_keys=True) + "\n")
        _atomic_write(paths["candidate"], json.dumps(candidate, indent=2, sort_keys=True) + "\n")
        _atomic_write(
            paths["validation"],
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "module_version": MODULE_VERSION,
                    "blueprint_validation": blueprint_validation,
                    "candidate_validation": candidate_validation,
                    "research_validation": {
                        "status": "READY_FOR_CENTRAL_ORCHESTRATOR_RESEARCH_VALIDATION",
                        "fixture_evidence_not_empirical": True,
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        _atomic_write(paths["proposal"], json.dumps(proposal, indent=2, sort_keys=True) + "\n")
    result.update(
        {
            "status": "SYNTHESIS_READY_FOR_RESEARCH_VALIDATION",
            "blueprint_created": True,
            "blueprint_id": blueprint["blueprint_id"],
            "blueprint_validation": blueprint_validation,
            "research_only_candidate_created": True,
            "candidate_id": candidate["candidate_id"],
            "candidate_validation": candidate_validation,
            "promotion_proposal_created": True,
            "artifact_paths": {
                **result["artifact_paths"],
                "blueprint": repo_relative(paths["blueprint"]),
                "candidate": repo_relative(paths["candidate"]),
                "validation": repo_relative(paths["validation"]),
                "proposal": repo_relative(paths["proposal"]),
            },
        }
    )
    return result


__all__ = [
    "ALLOWED_PRIMITIVES",
    "MAX_TUNABLE_PARAMETERS",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "build_registration_proposal",
    "build_research_only_candidate",
    "build_strategy_blueprint",
    "materialize_synthesis_readiness",
    "readiness_artifact_path",
    "run_bounded_strategy_synthesis",
    "stable_digest",
    "validate_blueprint",
    "validate_candidate",
]
