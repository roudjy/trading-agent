"""Campaign template catalog — frozen config for the v3.15.2 operating layer.

A template describes *what* the policy engine may spawn for a given
preset and campaign type. It is pure configuration — no strategy work,
no evaluation work — and exists strictly to answer:

- When does this campaign fire (cron tick, parent completion, weekly
  retest)?
- How often may it fire (cooldown + daily cap)?
- Which preset fields gate eligibility?
- What is the baseline runtime estimate (fallback for a cold ledger)?
- What follow-up rules are allowed to derive children from this
  campaign's outcome?

All templates ship in the closed catalog ``CAMPAIGN_TEMPLATES``.
Downstream code treats the catalog as frozen: picking or scheduling a
template that is not in the catalog is a bug, not a configuration
mistake.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from research.campaign_os_artifacts import build_pin_block

TEMPLATES_SCHEMA_VERSION: str = "1.0"

CampaignType = Literal[
    "daily_primary",
    "daily_control",
    "survivor_confirmation",
    "paper_followup",
    "weekly_retest",
]

CAMPAIGN_TYPES: tuple[str, ...] = (
    "daily_primary",
    "daily_control",
    "survivor_confirmation",
    "paper_followup",
    "weekly_retest",
)

# Cooldowns are defaults; the preset-policy state layer may widen them.
_DEFAULT_DAILY_PRIMARY_COOLDOWN_S: int = 86_400
_DEFAULT_DAILY_CONTROL_COOLDOWN_S: int = 604_800
_DEFAULT_SURVIVOR_CONFIRMATION_COOLDOWN_S: int = 43_200
_DEFAULT_PAPER_FOLLOWUP_MIN_GAP_S: int = 3_600
_DEFAULT_WEEKLY_RETEST_COOLDOWN_S: int = 604_800

# Runtime budget defaults. The estimator in campaign_budget overrides
# these as soon as the ledger has enough history.
_DEFAULT_DAILY_COMPUTE_BUDGET_S: int = 57_600  # 16 h
_DEFAULT_RESERVED_FOLLOWUP_S: int = 17_280  # 30% of daily budget
_DEFAULT_ESTIMATED_RUNTIME_S: int = 1_800
_DEFAULT_LEASE_TTL_S: int = 7_200
_DEFAULT_LEDGER_ROTATION_BYTES: int = 52_428_800  # 50 MB
_DEFAULT_MAX_LOW_VALUE_RERUNS: int = 2
_DEFAULT_TIER1_FAIRNESS_CAP: int = 4


@dataclass(frozen=True)
class EligibilityPredicate:
    """Preset-field gates that a candidate template must satisfy."""

    require_preset_enabled: bool = True
    forbid_excluded_from_daily_scheduler: bool = False
    forbid_diagnostic_only: bool = False
    require_preset_status: tuple[str, ...] = field(default_factory=tuple)
    require_parent_outcome: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CampaignTemplate:
    """Frozen template descriptor consumed by the policy engine."""

    template_id: str
    preset_name: str
    campaign_type: CampaignType
    priority_tier: int
    cooldown_seconds: int
    max_per_day: int
    eligibility: EligibilityPredicate
    estimated_runtime_seconds_default: int
    spawn_triggers: tuple[str, ...]
    followup_rules: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["eligibility"] = self.eligibility.to_payload()
        return data


@dataclass(frozen=True)
class CampaignOsConfig:
    """Top-level COL configuration baked into the templates artifact."""

    daily_compute_budget_seconds: int = _DEFAULT_DAILY_COMPUTE_BUDGET_S
    reserved_for_followups_seconds: int = _DEFAULT_RESERVED_FOLLOWUP_S
    max_concurrent_campaigns: int = 1
    max_low_value_reruns_per_day: int = _DEFAULT_MAX_LOW_VALUE_RERUNS
    estimated_runtime_fallback_seconds: int = _DEFAULT_ESTIMATED_RUNTIME_S
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_S
    ledger_rotation_bytes: int = _DEFAULT_LEDGER_ROTATION_BYTES
    tier1_fairness_cap: int = _DEFAULT_TIER1_FAIRNESS_CAP

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Frozen catalog — the only presets exposed to v3.15.2 autonomous policy.
# ---------------------------------------------------------------------------


def _daily_primary(preset_name: str) -> CampaignTemplate:
    return CampaignTemplate(
        template_id=f"daily_primary__{preset_name}",
        preset_name=preset_name,
        campaign_type="daily_primary",
        priority_tier=2,
        cooldown_seconds=_DEFAULT_DAILY_PRIMARY_COOLDOWN_S,
        max_per_day=1,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
            forbid_excluded_from_daily_scheduler=True,
            forbid_diagnostic_only=True,
            require_preset_status=("stable",),
        ),
        estimated_runtime_seconds_default=_DEFAULT_ESTIMATED_RUNTIME_S,
        spawn_triggers=("cron_tick",),
        followup_rules=(
            "survivor_confirmation_if_survivor",
            "paper_followup_if_blocked",
            "daily_control_weekly",
        ),
    )


def _daily_control(preset_name: str) -> CampaignTemplate:
    return CampaignTemplate(
        template_id=f"daily_control__{preset_name}",
        preset_name=preset_name,
        campaign_type="daily_control",
        priority_tier=3,
        cooldown_seconds=_DEFAULT_DAILY_CONTROL_COOLDOWN_S,
        max_per_day=1,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
            require_preset_status=("stable",),
        ),
        estimated_runtime_seconds_default=_DEFAULT_ESTIMATED_RUNTIME_S,
        spawn_triggers=("cron_tick",),
        followup_rules=(),
    )


def _survivor_confirmation(preset_name: str) -> CampaignTemplate:
    return CampaignTemplate(
        template_id=f"survivor_confirmation__{preset_name}",
        preset_name=preset_name,
        campaign_type="survivor_confirmation",
        priority_tier=1,
        cooldown_seconds=_DEFAULT_SURVIVOR_CONFIRMATION_COOLDOWN_S,
        max_per_day=3,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
            require_parent_outcome=("completed_with_candidates",),
        ),
        estimated_runtime_seconds_default=_DEFAULT_ESTIMATED_RUNTIME_S,
        spawn_triggers=("parent_completed",),
        followup_rules=("paper_followup_if_blocked",),
    )


def _paper_followup(preset_name: str) -> CampaignTemplate:
    return CampaignTemplate(
        template_id=f"paper_followup__{preset_name}",
        preset_name=preset_name,
        campaign_type="paper_followup",
        priority_tier=1,
        cooldown_seconds=_DEFAULT_PAPER_FOLLOWUP_MIN_GAP_S,
        max_per_day=2,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
        ),
        estimated_runtime_seconds_default=_DEFAULT_ESTIMATED_RUNTIME_S,
        spawn_triggers=("parent_paper_blocked",),
        followup_rules=(),
    )


def _weekly_retest(preset_name: str) -> CampaignTemplate:
    return CampaignTemplate(
        template_id=f"weekly_retest__{preset_name}",
        preset_name=preset_name,
        campaign_type="weekly_retest",
        priority_tier=3,
        cooldown_seconds=_DEFAULT_WEEKLY_RETEST_COOLDOWN_S,
        max_per_day=1,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
        ),
        estimated_runtime_seconds_default=_DEFAULT_ESTIMATED_RUNTIME_S,
        spawn_triggers=("cron_tick",),
        followup_rules=(),
    )


_BASELINE_PRESETS: tuple[str, ...] = (
    "trend_equities_4h_baseline",
    "trend_regime_filtered_equities_4h",
    "crypto_diagnostic_1h",
)


def _build_default_catalog() -> tuple[CampaignTemplate, ...]:
    templates: list[CampaignTemplate] = []
    for preset_name in _BASELINE_PRESETS:
        templates.extend(
            (
                _daily_primary(preset_name),
                _daily_control(preset_name),
                _survivor_confirmation(preset_name),
                _paper_followup(preset_name),
                _weekly_retest(preset_name),
            )
        )
    return tuple(sorted(templates, key=lambda t: t.template_id))


CAMPAIGN_TEMPLATES: tuple[CampaignTemplate, ...] = _build_default_catalog()
DEFAULT_CONFIG: CampaignOsConfig = CampaignOsConfig()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates(
    catalog: tuple[CampaignTemplate, ...] = CAMPAIGN_TEMPLATES,
) -> list[CampaignTemplate]:
    return list(catalog)


def get_template(
    template_id: str,
    *,
    catalog: tuple[CampaignTemplate, ...] = CAMPAIGN_TEMPLATES,
) -> CampaignTemplate:
    for template in catalog:
        if template.template_id == template_id:
            return template
    raise KeyError(f"unknown template_id {template_id!r}")


def templates_for_type(
    campaign_type: CampaignType,
    *,
    catalog: tuple[CampaignTemplate, ...] = CAMPAIGN_TEMPLATES,
) -> list[CampaignTemplate]:
    return [t for t in catalog if t.campaign_type == campaign_type]


def build_templates_payload(
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    catalog: tuple[CampaignTemplate, ...] = CAMPAIGN_TEMPLATES,
    config: CampaignOsConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Assemble the catalog artifact payload with pin block + config."""
    pins = build_pin_block(
        schema_version=TEMPLATES_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    return {
        **pins,
        "config": config.to_payload(),
        "templates": [t.to_payload() for t in catalog],
    }


__all__ = [
    "CAMPAIGN_TEMPLATES",
    "CAMPAIGN_TYPES",
    "CampaignOsConfig",
    "CampaignTemplate",
    "CampaignType",
    "DEFAULT_CONFIG",
    "EligibilityPredicate",
    "TEMPLATES_SCHEMA_VERSION",
    "build_templates_payload",
    "get_template",
    "list_templates",
    "templates_for_type",
]
