"""Single source of truth for observability paths and constants.

Every other module in ``research.observability`` consumes the
constants defined here. Path values are written as ``Path`` literals,
NOT imported from the writer modules — this guarantees zero coupling
to runtime/decision modules. A drift test
(``tests/unit/test_observability_paths.py``) verifies that these
literal paths still match the writer modules' constants by parsing
those files as TEXT (no ``import``).

Hard rule: this module imports only ``pathlib``. No other project
module is imported here.
"""

from __future__ import annotations

from pathlib import Path

# --- Repo layout anchors ---------------------------------------------------

# All paths are relative to the project root. The CLI / writers expect
# the cwd to be the repo root (consistent with how the rest of the
# project resolves ``research/...`` paths).
RESEARCH_DIR: Path = Path("research")
OBSERVABILITY_DIR: Path = RESEARCH_DIR / "observability"

# --- Output artifacts (written by this package) ----------------------------

# Schema version of the observability artifacts written by v3.15.15.2.
# Bumping requires updating consumer adapters; consumers MUST tolerate
# unknown fields (additive evolution).
OBSERVABILITY_SCHEMA_VERSION: str = "1.0"

ARTIFACT_HEALTH_PATH: Path = OBSERVABILITY_DIR / "artifact_health_latest.v1.json"
FAILURE_MODES_PATH: Path = OBSERVABILITY_DIR / "failure_modes_latest.v1.json"
THROUGHPUT_METRICS_PATH: Path = OBSERVABILITY_DIR / "throughput_metrics_latest.v1.json"
SYSTEM_INTEGRITY_PATH: Path = OBSERVABILITY_DIR / "system_integrity_latest.v1.json"
OBSERVABILITY_SUMMARY_PATH: Path = OBSERVABILITY_DIR / "observability_summary_latest.v1.json"

# Components in the v3.15.15.2 release. Six more
# (funnel_stage_summary, campaign_timeline, parameter_coverage,
# data_freshness, policy_decision_trace, no_touch_health) are reserved
# for a future release; they are listed below in
# ``DEFERRED_COMPONENTS`` so the aggregator can report them as
# ``unavailable`` rather than ``unknown``.

# (component_name, slug, output_path)
ACTIVE_COMPONENTS: tuple[tuple[str, str, Path], ...] = (
    ("artifact_health", "artifact-health", ARTIFACT_HEALTH_PATH),
    ("failure_modes", "failure-modes", FAILURE_MODES_PATH),
    ("throughput_metrics", "throughput", THROUGHPUT_METRICS_PATH),
    ("system_integrity", "system-integrity", SYSTEM_INTEGRITY_PATH),
)

# Components reserved for v3.15.15.4. The aggregator surfaces these as
# ``unavailable`` so frontends can render an "Unavailable — pending
# release" badge without crashing.
DEFERRED_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("funnel_stage_summary", "funnel"),
    ("campaign_timeline", "campaign-timeline"),
    ("parameter_coverage", "parameter-coverage"),
    ("data_freshness", "data-freshness"),
    ("policy_decision_trace", "policy-trace"),
    ("no_touch_health", "no-touch-health"),
)

# --- Input artifacts (read by this package; NEVER mutated) -----------------

# (canonical_name, contract_class, path)
#
# contract_class values:
#   "frozen_public_contract"  — research_latest.json, strategy_matrix.csv
#   "campaign_artifact"       — registry / queue / digest / templates
#   "evidence_artifact"       — campaign_evidence_ledger / screening_evidence
#   "sprint_artifact"         — discovery sprint registry / progress / report
#   "observability_sidecar"   — anything under research/observability/
#   "research_meta_artifact"  — public_artifact_status, run_state, run_*

INPUT_ARTIFACTS: tuple[tuple[str, str, Path], ...] = (
    # Frozen public contracts. Inspected for size/mtime/parse_ok only.
    (
        "research_latest.json",
        "frozen_public_contract",
        RESEARCH_DIR / "research_latest.json",
    ),
    (
        "strategy_matrix.csv",
        "frozen_public_contract",
        RESEARCH_DIR / "strategy_matrix.csv",
    ),
    # Public-artifact freshness sidecar.
    (
        "public_artifact_status_latest.v1.json",
        "research_meta_artifact",
        RESEARCH_DIR / "public_artifact_status_latest.v1.json",
    ),
    # Campaign Operating Layer artifacts.
    (
        "campaign_registry_latest.v1.json",
        "campaign_artifact",
        RESEARCH_DIR / "campaign_registry_latest.v1.json",
    ),
    (
        "campaign_queue_latest.v1.json",
        "campaign_artifact",
        RESEARCH_DIR / "campaign_queue_latest.v1.json",
    ),
    (
        "campaign_digest_latest.v1.json",
        "campaign_artifact",
        RESEARCH_DIR / "campaign_digest_latest.v1.json",
    ),
    (
        "screening_evidence_latest.v1.json",
        "evidence_artifact",
        RESEARCH_DIR / "screening_evidence_latest.v1.json",
    ),
    # Campaign evidence ledger (JSONL — append-only event stream).
    # v3.15.15.7 — fixed canonical filename to match the launcher's writer
    # constant in ``research/campaign_launcher.py:139``.
    (
        "campaign_evidence_ledger_latest.v1.jsonl",
        "evidence_artifact",
        RESEARCH_DIR / "campaign_evidence_ledger_latest.v1.jsonl",
    ),
    # Rolled-up evidence snapshot (v3.15.11).
    (
        "evidence_ledger_latest.v1.json",
        "evidence_artifact",
        RESEARCH_DIR / "campaigns" / "evidence" / "evidence_ledger_latest.v1.json",
    ),
    # Spawn proposals (v3.15.12).
    (
        "spawn_proposals_latest.v1.json",
        "evidence_artifact",
        RESEARCH_DIR / "campaigns" / "evidence" / "spawn_proposals_latest.v1.json",
    ),
    # Discovery sprint sidecars.
    (
        "sprint_registry_latest.v1.json",
        "sprint_artifact",
        RESEARCH_DIR / "discovery_sprints" / "sprint_registry_latest.v1.json",
    ),
    (
        "discovery_sprint_progress_latest.v1.json",
        "sprint_artifact",
        RESEARCH_DIR / "discovery_sprints" / "discovery_sprint_progress_latest.v1.json",
    ),
    (
        "discovery_sprint_report_latest.v1.json",
        "sprint_artifact",
        RESEARCH_DIR / "discovery_sprints" / "discovery_sprint_report_latest.v1.json",
    ),
)

# Path used by failure_modes for the bounded JSONL ledger read. Kept
# separate from INPUT_ARTIFACTS so failure_modes does not depend on
# the entire input map.
# v3.15.15.7 — bug fix: the launcher writes the campaign event ledger to
# ``research/campaign_evidence_ledger_latest.v1.jsonl`` (the project-wide
# ``_latest.v1`` snapshot-current convention). Pre-v3.15.15.7 this constant
# was missing the ``_latest.v1`` suffix, causing ``read_jsonl_tail_safe``
# to find no file and report ``ledger_available=false`` even though the
# launcher had been writing the artifact since the project's start. The
# corresponding writer constant is ``EVIDENCE_LEDGER_PATH`` defined in
# ``research/campaign_launcher.py:139``; the path-drift test in
# ``tests/unit/test_observability_paths.py`` pins both sides as text so a
# future rename on either side fails loudly.
CAMPAIGN_EVIDENCE_LEDGER_PATH: Path = RESEARCH_DIR / "campaign_evidence_ledger_latest.v1.jsonl"
CAMPAIGN_REGISTRY_PATH: Path = RESEARCH_DIR / "campaign_registry_latest.v1.json"

# --- Bounded read constants ------------------------------------------------

# Maximum number of trailing lines to read from the campaign evidence
# ledger. Beyond this, observability output is bounded and labeled as
# "within last N events", never claimed as global totals. This keeps:
#   * memory bounded (no OOM after long uptime),
#   * outputs deterministic for a given (input, cap),
#   * compute bounded (one pass, fixed work).
MAX_LEDGER_LINES: int = 10_000

# Maximum bytes to read backwards from the end of the ledger when
# locating MAX_LEDGER_LINES line breaks. Belt-and-braces guard.
MAX_LEDGER_TAIL_BYTES: int = 25 * 1024 * 1024  # 25 MB

# --- Staleness thresholds --------------------------------------------------
#
# Used by artifact_health to classify stale vs fresh. Conservative
# defaults; observability is descriptive — these are reporting
# thresholds, NOT enforcement thresholds.

STALE_THRESHOLD_SECONDS: dict[str, int] = {
    "frozen_public_contract": 7 * 24 * 3600,    # 7 days
    "campaign_artifact":      4 * 3600,         # 4 hours
    "evidence_artifact":      4 * 3600,         # 4 hours
    "sprint_artifact":        24 * 3600,        # 24 hours
    "research_meta_artifact": 4 * 3600,         # 4 hours
    "observability_sidecar":  60 * 60,          # 1 hour (own outputs)
}

DEFAULT_STALE_THRESHOLD_SECONDS: int = 24 * 3600


def stale_threshold_for(contract_class: str) -> int:
    """Return the staleness threshold in seconds for a contract class."""
    return STALE_THRESHOLD_SECONDS.get(contract_class, DEFAULT_STALE_THRESHOLD_SECONDS)


# v3.15.15.6 — Sprint-progress vs campaign-registry staleness threshold.
#
# When ``discovery_sprint_progress_latest.v1.json`` is older than
# ``campaign_registry_latest.v1.json`` by more than this many seconds,
# the aggregator emits a warning ``sprint_progress_stale_relative_to_registry``
# with the actual delta. This is a **warning ONLY** — it never sets
# ``infrastructure_status`` to degraded (sprint progress is a sidecar,
# not infrastructure). Default: 1 hour. Active sprints update progress
# at least hourly via the launcher tick.
SPRINT_PROGRESS_STALE_VS_REGISTRY_SECONDS: int = 60 * 60


# v3.15.15.6 — diagnostic_context vocabulary.
#
# Listed here as the single source of truth so unit tests, the
# aggregator's warning propagation, and the future-writer-enrichment
# tracker can refer to the same string keys.

DIAGNOSTIC_MODES: tuple[str, ...] = (
    "registry_only",
    "registry_plus_queue",
    "registry_plus_digest_enriched",
    "ledger_enriched",
    "screening_evidence_enriched",
    "full_funnel_evidence",
)

DIAGNOSTIC_EVIDENCE_STATUSES: tuple[str, ...] = (
    "sufficient",
    "partial",
    "insufficient",
    "unavailable",
)

# Documented limitation codes the diagnostics layer may emit. Any
# string in ``diagnostic_context.limitations`` should appear here so
# consumers (frontend, alerting) can render stable text for each.
DIAGNOSTIC_LIMITATION_CODES: tuple[str, ...] = (
    "registry_only_mode",
    "registry_plus_digest_only_mode",
    "campaign_evidence_ledger_absent",
    "screening_evidence_absent",
    "spawn_proposals_absent",
    "rolled_up_evidence_ledger_absent",
    "failure_reason_detail_unavailable",
    "asset_timeframe_fields_absent",
    "hypothesis_id_missing_from_source_artifact",
    "strategy_family_field_present_but_unpopulated_by_writer",
    "asset_class_field_present_but_unpopulated_by_writer",
    "timeframe_derivable_from_preset_only",
    "sprint_progress_stale_relative_to_registry",
    "conflicting_failure_reason_fields",
    "registry_absent",
    "registry_corrupt",
)


__all__ = [
    "ACTIVE_COMPONENTS",
    "ARTIFACT_HEALTH_PATH",
    "CAMPAIGN_EVIDENCE_LEDGER_PATH",
    "CAMPAIGN_REGISTRY_PATH",
    "DEFAULT_STALE_THRESHOLD_SECONDS",
    "DEFERRED_COMPONENTS",
    "DIAGNOSTIC_EVIDENCE_STATUSES",
    "DIAGNOSTIC_LIMITATION_CODES",
    "DIAGNOSTIC_MODES",
    "FAILURE_MODES_PATH",
    "INPUT_ARTIFACTS",
    "MAX_LEDGER_LINES",
    "MAX_LEDGER_TAIL_BYTES",
    "OBSERVABILITY_DIR",
    "OBSERVABILITY_SCHEMA_VERSION",
    "OBSERVABILITY_SUMMARY_PATH",
    "RESEARCH_DIR",
    "SPRINT_PROGRESS_STALE_VS_REGISTRY_SECONDS",
    "STALE_THRESHOLD_SECONDS",
    "SYSTEM_INTEGRITY_PATH",
    "THROUGHPUT_METRICS_PATH",
    "stale_threshold_for",
]
