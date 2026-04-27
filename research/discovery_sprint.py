"""v3.15.13 — Discovery Sprint Orchestrator (artifact-only).

A discovery sprint is a bounded, profile-driven observation window over
the existing v3.15.2 Campaign Operating Layer (COL). It does NOT spawn,
queue, lease, or otherwise mutate campaigns — COL keeps owning that.
This module:

1. Validates a closed built-in profile (currently ``crypto_exploratory_v1``).
2. Derives a deterministic plan from the existing
   ``research.strategy_hypothesis_catalog`` and ``research.presets``
   binding (no new strategies, no new presets).
3. Writes a sprint registry artifact that bounds an observation window
   (``target_campaigns`` over ``max_days``).
4. Reads ``research/campaign_registry_latest.v1.json`` (read-only) to
   count COL-completed campaigns whose preset is in the plan and whose
   ``finished_at_utc`` is inside the sprint window. Writes
   ``discovery_sprint_progress_latest.v1.json``.
5. When the target is met OR the window expires, transitions sprint
   state to ``completed`` and writes ``discovery_sprint_report_latest.v1.json``.

Hard constraints honoured:

- No mutations of: ``campaign_registry_latest.v1.json``,
  ``campaign_queue_latest.v1.json``, the ledger JSONL/meta, frozen
  contracts (``research_latest.json``, ``strategy_matrix.csv``), or any
  other v3.15.x sidecar.
- Cannot bypass COL — exposes no spawn surface.
- Idempotent ``run``: refuses to start a second sprint while another is
  ``active`` and within its window.
- Deterministic ``plan``: same inputs → byte-identical output.

CLI::

    python -m research.discovery_sprint plan   --profile crypto_exploratory_v1
    python -m research.discovery_sprint run    --profile crypto_exploratory_v1
    python -m research.discovery_sprint status
    python -m research.discovery_sprint report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_os_artifacts import build_pin_block, iso_utc
from research.campaign_registry import REGISTRY_ARTIFACT_PATH, load_registry
from research.presets import PRESETS, ResearchPreset
from research.strategy_hypothesis_catalog import (
    STRATEGY_HYPOTHESIS_CATALOG,
    StrategyHypothesis,
)


# ── constants ─────────────────────────────────────────────────────────

SPRINT_SCHEMA_VERSION: Final[str] = "1.0"

SPRINT_ARTIFACTS_DIR: Final[Path] = Path("research/discovery_sprints")
SPRINT_REGISTRY_PATH: Final[Path] = (
    SPRINT_ARTIFACTS_DIR / "sprint_registry_latest.v1.json"
)
SPRINT_PROGRESS_PATH: Final[Path] = (
    SPRINT_ARTIFACTS_DIR / "discovery_sprint_progress_latest.v1.json"
)
SPRINT_REPORT_PATH: Final[Path] = (
    SPRINT_ARTIFACTS_DIR / "discovery_sprint_report_latest.v1.json"
)

SprintState = Literal["active", "completed", "expired"]
SPRINT_STATES: Final[tuple[str, ...]] = ("active", "completed", "expired")

AssetClass = Literal["crypto", "equity"]
ASSET_CLASSES: Final[tuple[str, ...]] = ("crypto", "equity")

# Closed-set vocabulary mirrored from research.presets.ScreeningPhase.
SCREENING_PHASES: Final[tuple[str, ...]] = (
    "exploratory",
    "standard",
    "promotion_grade",
)

CRYPTO_QUOTE_TOKENS: Final[tuple[str, ...]] = (
    "EUR",
    "USD",
    "USDT",
    "USDC",
    "BUSD",
)


# ── data classes ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SprintProfile:
    """Closed profile descriptor. All fields are part of the contract."""

    name: str
    target_campaigns: int
    max_days: int
    asset_class: AssetClass
    timeframes: tuple[str, ...]
    screening_phase: str
    hypotheses: tuple[str, ...]
    exclude_equities: bool
    exclude_promotion_grade: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_campaigns": int(self.target_campaigns),
            "max_days": int(self.max_days),
            "asset_class": self.asset_class,
            "timeframes": list(self.timeframes),
            "screening_phase": self.screening_phase,
            "hypotheses": list(self.hypotheses),
            "exclude_equities": bool(self.exclude_equities),
            "exclude_promotion_grade": bool(self.exclude_promotion_grade),
        }


@dataclass(frozen=True)
class PlanEntry:
    """One eligible (preset × hypothesis × timeframe) tuple."""

    preset_name: str
    hypothesis_id: str
    strategy_family: str
    timeframe: str
    asset_class: AssetClass
    universe: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "preset_name": self.preset_name,
            "hypothesis_id": self.hypothesis_id,
            "strategy_family": self.strategy_family,
            "timeframe": self.timeframe,
            "asset_class": self.asset_class,
            "universe": list(self.universe),
        }


# ── built-in profiles ─────────────────────────────────────────────────

CRYPTO_EXPLORATORY_V1: Final[SprintProfile] = SprintProfile(
    name="crypto_exploratory_v1",
    target_campaigns=50,
    max_days=5,
    asset_class="crypto",
    timeframes=("1h", "4h"),
    screening_phase="exploratory",
    hypotheses=(
        "trend_pullback_v1",
        "volatility_compression_breakout_v0",
    ),
    exclude_equities=True,
    exclude_promotion_grade=True,
)

BUILTIN_PROFILES: Final[dict[str, SprintProfile]] = {
    CRYPTO_EXPLORATORY_V1.name: CRYPTO_EXPLORATORY_V1,
}


class ProfileError(ValueError):
    """Raised when a profile name is unknown or its content is invalid."""


def get_profile(name: str) -> SprintProfile:
    if name not in BUILTIN_PROFILES:
        raise ProfileError(
            f"unknown profile {name!r}; known={sorted(BUILTIN_PROFILES)}"
        )
    profile = BUILTIN_PROFILES[name]
    _validate_profile(profile)
    return profile


def _validate_profile(profile: SprintProfile) -> None:
    """Structural invariants. Raises ProfileError on any violation."""
    if profile.target_campaigns < 1:
        raise ProfileError("target_campaigns must be >= 1")
    if profile.max_days < 1:
        raise ProfileError("max_days must be >= 1")
    if profile.asset_class not in ASSET_CLASSES:
        raise ProfileError(
            f"asset_class must be in {ASSET_CLASSES}, got {profile.asset_class!r}"
        )
    if not profile.timeframes:
        raise ProfileError("timeframes must be non-empty")
    if profile.screening_phase not in SCREENING_PHASES:
        raise ProfileError(
            f"screening_phase must be in {SCREENING_PHASES}, "
            f"got {profile.screening_phase!r}"
        )
    if not profile.hypotheses:
        raise ProfileError("hypotheses must be non-empty")
    known = {h.hypothesis_id for h in STRATEGY_HYPOTHESIS_CATALOG}
    unknown = [h for h in profile.hypotheses if h not in known]
    if unknown:
        raise ProfileError(
            f"unknown hypotheses {unknown!r}; "
            f"catalog has {sorted(known)}"
        )
    if profile.asset_class == "crypto" and not profile.exclude_equities:
        raise ProfileError(
            "crypto profile must set exclude_equities=True"
        )
    if (
        profile.screening_phase == "exploratory"
        and not profile.exclude_promotion_grade
    ):
        raise ProfileError(
            "exploratory profile must set exclude_promotion_grade=True"
        )


# ── plan derivation ───────────────────────────────────────────────────


def _infer_asset_class(universe: tuple[str, ...]) -> AssetClass | None:
    """Return ``crypto`` if every symbol carries a known crypto quote
    suffix (e.g. ``BTC-EUR``), ``equity`` if no symbol does, else ``None``.
    """
    if not universe:
        return None
    crypto_count = 0
    for symbol in universe:
        upper = symbol.upper()
        if "-" in upper:
            quote = upper.rsplit("-", 1)[-1]
            if quote in CRYPTO_QUOTE_TOKENS:
                crypto_count += 1
    if crypto_count == len(universe):
        return "crypto"
    if crypto_count == 0:
        return "equity"
    return None  # mixed → require explicit treatment elsewhere


def _hypothesis_by_id(
    hypothesis_id: str,
    *,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> StrategyHypothesis | None:
    for hyp in catalog:
        if hyp.hypothesis_id == hypothesis_id:
            return hyp
    return None


def derive_plan(
    profile: SprintProfile,
    *,
    presets: tuple[ResearchPreset, ...] = PRESETS,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> tuple[PlanEntry, ...]:
    """Pure: profile + catalog + presets → ordered plan tuple.

    Filtering:

    - preset.hypothesis_id ∈ profile.hypotheses
    - preset.timeframe ∈ profile.timeframes
    - preset.screening_phase == profile.screening_phase
    - preset.enabled and preset.status == "stable"
    - preset universe asset class == profile.asset_class
    - if exclude_equities: drop any inferred ``equity``
    - if exclude_promotion_grade: drop any preset with
      ``screening_phase == "promotion_grade"`` (also covered by the
      phase equality check above; kept explicit for defensive clarity)
    """
    timeframes = set(profile.timeframes)
    allowed_hypotheses = set(profile.hypotheses)
    entries: list[PlanEntry] = []
    for preset in presets:
        if preset.hypothesis_id is None:
            continue
        if preset.hypothesis_id not in allowed_hypotheses:
            continue
        if preset.timeframe not in timeframes:
            continue
        if preset.screening_phase != profile.screening_phase:
            continue
        if (
            profile.exclude_promotion_grade
            and preset.screening_phase == "promotion_grade"
        ):
            continue
        if not preset.enabled or preset.status != "stable":
            continue
        inferred = _infer_asset_class(preset.universe)
        if inferred != profile.asset_class:
            continue
        if profile.exclude_equities and inferred == "equity":
            continue
        hyp = _hypothesis_by_id(preset.hypothesis_id, catalog=catalog)
        if hyp is None:
            continue
        entries.append(
            PlanEntry(
                preset_name=preset.name,
                hypothesis_id=preset.hypothesis_id,
                strategy_family=hyp.strategy_family,
                timeframe=preset.timeframe,
                asset_class=inferred,
                universe=tuple(preset.universe),
            )
        )
    entries.sort(
        key=lambda e: (e.hypothesis_id, e.timeframe, e.preset_name)
    )
    return tuple(entries)


# ── sprint id + payloads ──────────────────────────────────────────────


def compute_sprint_id(
    *,
    profile: SprintProfile,
    started_at_utc: datetime,
) -> str:
    payload = json.dumps(
        {
            "profile": profile.to_payload(),
            "started_at_utc": iso_utc(started_at_utc),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
    ts_compact = (
        started_at_utc.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    return f"sprt-{ts_compact}-{digest}"


def build_registry_payload(
    *,
    sprint_id: str,
    profile: SprintProfile,
    plan: tuple[PlanEntry, ...],
    started_at_utc: datetime,
    expected_completion_at_utc: datetime,
    state: SprintState,
    completed_at_utc: datetime | None,
    git_revision: str | None,
    generated_at_utc: datetime,
) -> dict[str, Any]:
    pins = build_pin_block(
        schema_version=SPRINT_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    return {
        **pins,
        "sprint_id": sprint_id,
        "state": state,
        "started_at_utc": iso_utc(started_at_utc),
        "expected_completion_at_utc": iso_utc(expected_completion_at_utc),
        "completed_at_utc": (
            iso_utc(completed_at_utc) if completed_at_utc else None
        ),
        "profile": profile.to_payload(),
        "plan": {
            "entry_count": len(plan),
            "entries": [e.to_payload() for e in plan],
        },
    }


def build_progress_payload(
    *,
    sprint_id: str,
    profile: SprintProfile,
    plan: tuple[PlanEntry, ...],
    observed: dict[str, Any],
    started_at_utc: datetime,
    expected_completion_at_utc: datetime,
    now_utc: datetime,
    git_revision: str | None,
) -> dict[str, Any]:
    pins = build_pin_block(
        schema_version=SPRINT_SCHEMA_VERSION,
        generated_at_utc=now_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    target = int(profile.target_campaigns)
    observed_total = int(observed.get("total") or 0)
    pct = (observed_total / target) if target > 0 else 0.0
    delta_to_expiry = expected_completion_at_utc - now_utc
    days_remaining = max(0.0, delta_to_expiry.total_seconds() / 86_400.0)
    target_met = observed_total >= target
    expired = now_utc >= expected_completion_at_utc
    return {
        **pins,
        "sprint_id": sprint_id,
        "started_at_utc": iso_utc(started_at_utc),
        "expected_completion_at_utc": iso_utc(expected_completion_at_utc),
        "now_utc": iso_utc(now_utc),
        "target_campaigns": target,
        "observed_total": observed_total,
        "pct_complete": round(pct, 4),
        "days_remaining": round(days_remaining, 4),
        "target_met": bool(target_met),
        "expired": bool(expired),
        "by_hypothesis": dict(observed.get("by_hypothesis") or {}),
        "by_preset": dict(observed.get("by_preset") or {}),
        "by_outcome": dict(observed.get("by_outcome") or {}),
        "plan_entry_count": len(plan),
    }


def build_report_payload(
    *,
    registry_payload: dict[str, Any],
    progress_payload: dict[str, Any],
    git_revision: str | None,
    now_utc: datetime,
) -> dict[str, Any]:
    pins = build_pin_block(
        schema_version=SPRINT_SCHEMA_VERSION,
        generated_at_utc=now_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    target = int(progress_payload.get("target_campaigns") or 0)
    observed = int(progress_payload.get("observed_total") or 0)
    shortfalls: list[str] = []
    if observed < target:
        shortfalls.append("target_campaigns_not_met")
    if progress_payload.get("expired") and observed < target:
        shortfalls.append("window_expired_with_shortfall")
    return {
        **pins,
        "sprint_id": registry_payload.get("sprint_id"),
        "profile": registry_payload.get("profile"),
        "plan": registry_payload.get("plan"),
        "state": registry_payload.get("state"),
        "started_at_utc": registry_payload.get("started_at_utc"),
        "expected_completion_at_utc": registry_payload.get(
            "expected_completion_at_utc"
        ),
        "completed_at_utc": registry_payload.get("completed_at_utc"),
        "outcome_summary": {
            "target_campaigns": target,
            "observed_total": observed,
            "target_met": bool(progress_payload.get("target_met")),
            "expired": bool(progress_payload.get("expired")),
            "by_hypothesis": dict(
                progress_payload.get("by_hypothesis") or {}
            ),
            "by_preset": dict(progress_payload.get("by_preset") or {}),
            "by_outcome": dict(progress_payload.get("by_outcome") or {}),
            "shortfall_codes": shortfalls,
        },
    }


# ── observation (pure over campaign_registry payload) ─────────────────


@dataclass
class ObservationCounts:
    total: int = 0
    by_hypothesis: dict[str, int] = field(default_factory=dict)
    by_preset: dict[str, int] = field(default_factory=dict)
    by_outcome: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "by_hypothesis": dict(self.by_hypothesis),
            "by_preset": dict(self.by_preset),
            "by_outcome": dict(self.by_outcome),
        }


def _parse_iso(ts: str | None) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def count_observations(
    *,
    campaign_registry: dict[str, Any],
    plan: tuple[PlanEntry, ...],
    started_at_utc: datetime,
    now_utc: datetime,
) -> ObservationCounts:
    """Return counts of completed COL campaigns that match the plan
    and finished inside ``[started_at_utc, now_utc]``."""
    counts = ObservationCounts()
    if not plan:
        return counts
    plan_presets = {e.preset_name: e for e in plan}
    campaigns = campaign_registry.get("campaigns") or {}
    iterable = (
        campaigns.values() if isinstance(campaigns, dict) else campaigns
    )
    started_aware = started_at_utc.astimezone(UTC)
    now_aware = now_utc.astimezone(UTC)
    for record in iterable:
        if not isinstance(record, dict):
            continue
        if record.get("state") != "completed":
            continue
        preset_name = str(record.get("preset_name") or "")
        if preset_name not in plan_presets:
            continue
        finished_at = _parse_iso(record.get("finished_at_utc"))
        if finished_at is None:
            continue
        finished_aware = finished_at.astimezone(UTC)
        if finished_aware < started_aware or finished_aware > now_aware:
            continue
        counts.total += 1
        plan_entry = plan_presets[preset_name]
        counts.by_hypothesis[plan_entry.hypothesis_id] = (
            counts.by_hypothesis.get(plan_entry.hypothesis_id, 0) + 1
        )
        counts.by_preset[preset_name] = (
            counts.by_preset.get(preset_name, 0) + 1
        )
        outcome = str(record.get("outcome") or "unknown")
        counts.by_outcome[outcome] = counts.by_outcome.get(outcome, 0) + 1
    return counts


# ── persistence helpers ───────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def load_sprint_registry(
    path: Path | None = None,
) -> dict[str, Any] | None:
    return _read_json(path if path is not None else SPRINT_REGISTRY_PATH)


def load_sprint_progress(
    path: Path | None = None,
) -> dict[str, Any] | None:
    return _read_json(path if path is not None else SPRINT_PROGRESS_PATH)


def _restore_profile(payload: dict[str, Any]) -> SprintProfile:
    return SprintProfile(
        name=str(payload["name"]),
        target_campaigns=int(payload["target_campaigns"]),
        max_days=int(payload["max_days"]),
        asset_class=str(payload["asset_class"]),  # type: ignore[arg-type]
        timeframes=tuple(payload.get("timeframes") or ()),
        screening_phase=str(payload["screening_phase"]),
        hypotheses=tuple(payload.get("hypotheses") or ()),
        exclude_equities=bool(payload.get("exclude_equities", False)),
        exclude_promotion_grade=bool(
            payload.get("exclude_promotion_grade", False)
        ),
    )


def _restore_plan(payload: dict[str, Any]) -> tuple[PlanEntry, ...]:
    entries_raw = payload.get("plan", {}).get("entries") or []
    out: list[PlanEntry] = []
    for entry in entries_raw:
        out.append(
            PlanEntry(
                preset_name=str(entry["preset_name"]),
                hypothesis_id=str(entry["hypothesis_id"]),
                strategy_family=str(entry["strategy_family"]),
                timeframe=str(entry["timeframe"]),
                asset_class=str(entry["asset_class"]),  # type: ignore[arg-type]
                universe=tuple(entry.get("universe") or ()),
            )
        )
    return tuple(out)


def _expected_completion(
    started_at_utc: datetime, max_days: int
) -> datetime:
    return started_at_utc.astimezone(UTC) + timedelta(days=int(max_days))


def is_active_sprint(
    *,
    registry_payload: dict[str, Any] | None,
    now_utc: datetime,
) -> bool:
    """True iff the registry has a sprint in state==active that has
    not yet passed its ``expected_completion_at_utc``."""
    if not registry_payload:
        return False
    if registry_payload.get("state") != "active":
        return False
    expected = _parse_iso(registry_payload.get("expected_completion_at_utc"))
    if expected is None:
        return True
    return now_utc.astimezone(UTC) < expected.astimezone(UTC)


# ── command handlers ──────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _git_revision() -> str | None:
    """Best-effort short rev. Avoids importing git; reads .git/HEAD."""
    try:
        head = Path(".git/HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        try:
            return Path(f".git/{ref}").read_text(encoding="utf-8").strip()[:12]
        except OSError:
            return None
    return head[:12] if head else None


def cmd_plan(profile_name: str, *, out=sys.stdout) -> int:
    try:
        profile = get_profile(profile_name)
    except ProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    plan = derive_plan(profile)
    summary = {
        "profile": profile.to_payload(),
        "plan": {
            "entry_count": len(plan),
            "entries": [e.to_payload() for e in plan],
        },
    }
    out.write(
        json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2)
    )
    out.write("\n")
    if not plan:
        return 2
    return 0


def cmd_run(profile_name: str, *, out=sys.stdout) -> int:
    try:
        profile = get_profile(profile_name)
    except ProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    now = _now_utc()
    existing = load_sprint_registry()
    if is_active_sprint(registry_payload=existing, now_utc=now):
        sid = (existing or {}).get("sprint_id")
        print(
            f"REFUSED: active sprint already exists (sprint_id={sid!r})",
            file=sys.stderr,
        )
        return 1
    plan = derive_plan(profile)
    if not plan:
        print(
            "ERROR: profile produced an empty plan; nothing would be observed",
            file=sys.stderr,
        )
        return 2
    sprint_id = compute_sprint_id(profile=profile, started_at_utc=now)
    expected_completion = _expected_completion(now, profile.max_days)
    git_rev = _git_revision()
    registry_payload = build_registry_payload(
        sprint_id=sprint_id,
        profile=profile,
        plan=plan,
        started_at_utc=now,
        expected_completion_at_utc=expected_completion,
        state="active",
        completed_at_utc=None,
        git_revision=git_rev,
        generated_at_utc=now,
    )
    write_sidecar_atomic(SPRINT_REGISTRY_PATH, registry_payload)
    progress_payload = build_progress_payload(
        sprint_id=sprint_id,
        profile=profile,
        plan=plan,
        observed=ObservationCounts().to_dict(),
        started_at_utc=now,
        expected_completion_at_utc=expected_completion,
        now_utc=now,
        git_revision=git_rev,
    )
    write_sidecar_atomic(SPRINT_PROGRESS_PATH, progress_payload)
    out.write(
        json.dumps(
            {
                "sprint_id": sprint_id,
                "state": "active",
                "started_at_utc": iso_utc(now),
                "expected_completion_at_utc": iso_utc(expected_completion),
                "plan_entry_count": len(plan),
            },
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        )
    )
    out.write("\n")
    return 0


def cmd_status(*, out=sys.stdout) -> int:
    registry_payload = load_sprint_registry()
    if not registry_payload:
        out.write(
            json.dumps(
                {"state": "no_sprint", "sprint_id": None},
                sort_keys=True,
                indent=2,
            )
        )
        out.write("\n")
        return 0
    profile = _restore_profile(registry_payload["profile"])
    plan = _restore_plan(registry_payload)
    started_at = _parse_iso(registry_payload.get("started_at_utc"))
    expected_completion = _parse_iso(
        registry_payload.get("expected_completion_at_utc")
    )
    if started_at is None or expected_completion is None:
        print("ERROR: registry artifact missing timestamps", file=sys.stderr)
        return 2
    now = _now_utc()
    campaign_registry = load_registry(REGISTRY_ARTIFACT_PATH)
    counts = count_observations(
        campaign_registry=campaign_registry,
        plan=plan,
        started_at_utc=started_at,
        now_utc=now,
    )
    git_rev = _git_revision()
    progress_payload = build_progress_payload(
        sprint_id=registry_payload["sprint_id"],
        profile=profile,
        plan=plan,
        observed=counts.to_dict(),
        started_at_utc=started_at,
        expected_completion_at_utc=expected_completion,
        now_utc=now,
        git_revision=git_rev,
    )
    write_sidecar_atomic(SPRINT_PROGRESS_PATH, progress_payload)
    target_met = bool(progress_payload["target_met"])
    expired = bool(progress_payload["expired"])
    if registry_payload.get("state") == "active" and (target_met or expired):
        new_state: SprintState = "completed" if target_met else "expired"
        registry_payload = build_registry_payload(
            sprint_id=registry_payload["sprint_id"],
            profile=profile,
            plan=plan,
            started_at_utc=started_at,
            expected_completion_at_utc=expected_completion,
            state=new_state,
            completed_at_utc=now,
            git_revision=git_rev,
            generated_at_utc=now,
        )
        write_sidecar_atomic(SPRINT_REGISTRY_PATH, registry_payload)
    out.write(
        json.dumps(
            {
                "sprint_id": registry_payload["sprint_id"],
                "state": registry_payload.get("state"),
                "started_at_utc": registry_payload.get("started_at_utc"),
                "expected_completion_at_utc": registry_payload.get(
                    "expected_completion_at_utc"
                ),
                "completed_at_utc": registry_payload.get("completed_at_utc"),
                "target_campaigns": progress_payload["target_campaigns"],
                "observed_total": progress_payload["observed_total"],
                "pct_complete": progress_payload["pct_complete"],
                "days_remaining": progress_payload["days_remaining"],
                "target_met": progress_payload["target_met"],
                "expired": progress_payload["expired"],
                "by_hypothesis": progress_payload["by_hypothesis"],
                "by_preset": progress_payload["by_preset"],
                "by_outcome": progress_payload["by_outcome"],
            },
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        )
    )
    out.write("\n")
    return 0


def cmd_report(*, out=sys.stdout) -> int:
    registry_payload = load_sprint_registry()
    if not registry_payload:
        print("ERROR: no sprint registry to report on", file=sys.stderr)
        return 2
    state = registry_payload.get("state")
    if state == "active":
        print(
            "ERROR: sprint is still active; run status first",
            file=sys.stderr,
        )
        return 1
    progress_payload = load_sprint_progress()
    if not progress_payload:
        print(
            "ERROR: no progress artifact found; run status first",
            file=sys.stderr,
        )
        return 2
    now = _now_utc()
    git_rev = _git_revision()
    report_payload = build_report_payload(
        registry_payload=registry_payload,
        progress_payload=progress_payload,
        git_revision=git_rev,
        now_utc=now,
    )
    write_sidecar_atomic(SPRINT_REPORT_PATH, report_payload)
    out.write(
        json.dumps(
            {
                "sprint_id": report_payload["sprint_id"],
                "state": state,
                "outcome_summary": report_payload["outcome_summary"],
            },
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        )
    )
    out.write("\n")
    return 0


# ── CLI entry ─────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.discovery_sprint",
        description=(
            "v3.15.13 Discovery Sprint Orchestrator — bounded, "
            "artifact-only observation window over the v3.15.2 COL."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser(
        "plan", help="Print a deterministic dry-run plan; no I/O."
    )
    p_plan.add_argument("--profile", required=True)
    p_run = sub.add_parser(
        "run", help="Start a sprint; refuses if one is already active."
    )
    p_run.add_argument("--profile", required=True)
    sub.add_parser(
        "status",
        help="Read registry + count observations; transitions state if target met or expired.",
    )
    sub.add_parser(
        "report",
        help="Write report artifact when sprint is completed/expired.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "plan":
        return cmd_plan(args.profile)
    if args.cmd == "run":
        return cmd_run(args.profile)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "report":
        return cmd_report()
    parser.error(f"unknown command {args.cmd!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())


__all__ = [
    "ASSET_CLASSES",
    "BUILTIN_PROFILES",
    "CRYPTO_EXPLORATORY_V1",
    "ObservationCounts",
    "PlanEntry",
    "ProfileError",
    "SCREENING_PHASES",
    "SPRINT_PROGRESS_PATH",
    "SPRINT_REGISTRY_PATH",
    "SPRINT_REPORT_PATH",
    "SPRINT_SCHEMA_VERSION",
    "SPRINT_STATES",
    "SprintProfile",
    "build_progress_payload",
    "build_registry_payload",
    "build_report_payload",
    "cmd_plan",
    "cmd_report",
    "cmd_run",
    "cmd_status",
    "compute_sprint_id",
    "count_observations",
    "derive_plan",
    "get_profile",
    "is_active_sprint",
    "load_sprint_progress",
    "load_sprint_registry",
    "main",
]
