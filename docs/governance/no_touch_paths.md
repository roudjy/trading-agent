# No-Touch Paths

Single source of truth for paths that **agents must not modify**. Mirror of
`.claude/hooks/deny_no_touch.py:NO_TOUCH_GLOBS`. The unit test
`tests/unit/test_hooks_no_touch.py` verifies that this document and the hook
constant stay in sync.

Three enforcement layers protect every entry below:

1. **Hook layer** (`deny_no_touch.py`) - fail-closed deny at the
   `PreToolUse Edit|Write` boundary.
2. **CODEOWNERS** - each path requires the repo owner's review for any PR
   that touches it.
3. **Branch protection** (configured in GitHub UI per
   [`branch_protection_checklist.md`](branch_protection_checklist.md)) - the
   `main` branch refuses force-push and requires Code Owners to approve.

A bypass requires **all three** to be relaxed in concert, which only happens
through a human-authored, CODEOWNERS-reviewed `governance-bootstrap` PR.

Revision 5 hardening: the no-touch list now covers full backend code
directories (`agent/{brain,execution,learning,agents,risk,monitoring}/**`,
`automation/**`, `execution/**`, `orchestration/**`, `research/**`,
`strategies/**`) and `dashboard/dashboard.py`. A second hook
(`deny_outside_agent_allowlist.py`) additionally enforces that any write
must be under at least one agent's frontmatter `allowed_roots`, with
default-deny when context is unknown.

---

## Read AND Write deny

These paths are forbidden to be opened, grepped, summarized, or included
in diffs by any agent. This is enforced by `deny_config_read.py`.

| Pattern | Why |
|---|---|
| `config/config.yaml` | Live credentials. |
| `state/*.secret` | Runtime secrets (live-gate HMAC seed, dashboard session secret). |
| `automation/*.secret` | Defense in depth. |
| `.env`, `.env.*` | Conventional secret stores. |

Indirect-read denials (Revision 5):

- `python -c` and `python --command` outright (chr() / base64 obfuscation).
- `eval`, `base64 -d` / `--decode`.
- Redirect reads (`< config/config.yaml`, `< .env`, `< state/*.secret`).
- Process substitution (`<(cat config/config.yaml)`).
- Command substitution (`$(cat config/...)`, `$(<config/...)`, backticks).
- Find with `-exec` on secret paths.
- `awk`, `sed`, `tac`, `od`, `xxd`, `hexdump`, `strings`, `cut`, `nl`,
  `dd if=`, `grep`, `rg` against secret paths.

---

## Write deny (read allowed for context)

### Live trading / capital
- `automation/live_gate.py` - the only barrier between paper and live.
- `automation/**` - full directory after R5.

### Authority surface (ADR-014)
- `research/authority_views.py`, `research/authority_trace.py`
- `research/candidate_lifecycle.py`, `research/candidate_pipeline.py`,
  `research/candidate_registry_v2.py`
- `research/campaign_funnel_policy.py`, `research/campaign_preset_policy.py`,
  `research/campaign_family_policy.py`
- `research/promotion.py`, `research/strategy_hypothesis_catalog.py`
- `research/campaign_evidence_ledger.py`, `research/research_evidence_ledger.py`
- `research/paper_ledger.py`, `research/screening_evidence.py`
- `research/**` - full directory after R5.

### Backend non-core (R5.2 - never agent-writable)
- `agent/brain/**` - signal aggregator, regime detection.
- `agent/execution/**` - order executor.
- `agent/learning/**` - reporter, self_improver, memory.
- `agent/agents/**` - the strategy agents themselves.
- `agent/risk/**`, `agent/monitoring/**` - capped risk and monitoring.
- `dashboard/dashboard.py` - reads operator session and token secrets.
- `execution/**`, `strategies/**` - trading-flow code.

### Orchestration core (ADR-009) and backtest core (ADR-007/008)
- `orchestration/orchestrator.py`
- `orchestration/**` - full directory after R5.
- `agent/backtesting/engine.py`, `agent/backtesting/fitted_features.py`

### Production posture
- `docker-compose.prod.yml`
- `scripts/deploy.sh`
- `ops/systemd/**`, `ops/nginx/**`
- `Dockerfile`

### Frozen v1 schemas
- `**/*_latest.v1.json`, `**/*_latest.v1.jsonl`

### ADRs
- `docs/adr/ADR-*.md` - existing ADRs are immutable; drafts go into
  `docs/adr/_drafts/` via the `ask` flow.

### Determinism pin tests
- `tests/regression/test_v3_*pin*.py`
- `tests/regression/test_v3_15_artifacts_deterministic.py`
- `tests/regression/test_authority_invariants.py`
- `tests/regression/test_v3_15_8_canonical_dump_and_digest.py`

### Governance layer (self-protected after seed)
- `.claude/settings.json`
- `.claude/hooks/**`
- `.claude/agents/**`
- `.github/CODEOWNERS`

### Version & release
- `VERSION` - bump only via Release-Gate-recommended human-approved PR.

### Governance core docs
Writable only by `planner`, `product-owner`, or `release-gate-agent` via the
allowlists in their agent frontmatter:

- `docs/governance/agent_governance.md`
- `docs/governance/autonomy_ladder.md`
- `docs/governance/no_touch_paths.md` (this file)
- `docs/governance/permission_model.md`
- `docs/governance/no_test_weakening.md`
- `docs/governance/hooks_runtime_policy.md`
- `docs/governance/provenance.md`
- `docs/governance/audit_chain.md`
- `docs/governance/release_gate.md`
- `docs/governance/release_gate_checklist.md`
- `docs/governance/rollback_drill.md`
- `docs/governance/sha_pin_review.md`

---

## Live-connector create-deny

Independent of the path/edit deny rules above, `deny_live_connector.py`
**blocks creation** of new files that match live-connector patterns:

- `execution/live/**`, `automation/live/**`, `agent/execution/live/**`
- `**/live_*broker*.py`, `**/*live*broker*.py`
- `**/*live_executor*.py`, `**/*live*executor*.py`
- `**/*_live.py`
- Any Python source file (anywhere) whose new content imports the
  Ethereum-account signing surface, calls a raw transaction sender,
  instantiates the Polymarket clob client with a private key, or calls a
  CCXT exchange's `create_order` without a paper-mode flag.

---

## Allowlist enforcement (Revision 5 - new layer)

Beyond no-touch, a second hook (`deny_outside_agent_allowlist.py`) requires
that any write target falls under at least one agent's frontmatter
`allowed_roots`. If the target is outside the union of all agents'
allowed_roots, the write is denied even when no NO_TOUCH glob matches.

The union is computed at hook load by parsing `.claude/agents/*.md`
frontmatter. If `.claude/agents/` is unreadable or empty, the hook
default-denies (fail-closed).

---

## `ask` paths (write requires explicit confirmation)

These are not no-touch but require operator approval via the `ask` flow in
`.claude/settings.json`:

- `.github/workflows/**` - only the `ci-guardian` agent should propose changes,
  and only inside a dedicated `ci-hardening` task.
- `pyproject.toml`
- `.gitignore`, `.dockerignore`
- `tests/regression/**` (anything other than the deny-listed pin tests)
- `CHANGELOG.md`
- `docs/adr/_drafts/**`

---

## Synchronization check

The CI job `hook-tests` runs `tests/unit/test_hooks_no_touch.py`, which
verifies that every glob in `NO_TOUCH_GLOBS` (in `deny_no_touch.py`) is also
documented in this file and vice-versa. If you change the hook constant
without updating this doc (or vice-versa), CI fails.

A complementary `governance-lint` CI job verifies that no agent declares
`max_autonomy_level > 3`, no GitHub Action uses a floating tag, and no
file mentions Level 6 as enabled.
