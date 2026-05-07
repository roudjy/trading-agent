# Autonomous Development Delegation (A11)

> Canonical governance document for the Bounded Roadmap
> Implementation Delegation introduced in A11. Read-only, pure
> marker parser. No fuzzy parsing.

## Status

Active. Modifications to this document require operator approval.

## What this is — and is not

A11 introduces a deterministic mechanism for turning explicit
roadmap items into routable delegation entries:

- explicit `<!-- ade_delegation ... -->` markers inside the two
  canonical roadmap docs;
- explicit JSONL entries inside the optional sidecar
  `docs/development_work_queue/delegation_seed.jsonl`.

A11 is **not**:

- a prose / heading / bullet-list parser,
- an NLP/LLM reasoner,
- an auto-promotion mechanism into the development work queue,
- a writer to `seed.jsonl` / `bugfix_seed.jsonl` /
  `delegation_seed.jsonl`.

`reporting.development_delegation` produces only
`logs/development_delegation/latest.json`. Promotion of any entry
into the queue's `seed.jsonl` is a separate manual operator
action — same discipline as A10.

## Marker syntax (canonical roadmap docs)

```
<!-- ade_delegation
delegation_id: <opaque-stable-id, [A-Za-z0-9_.-]+>
title: <≤200 chars>
category: <one of A8 CATEGORIES>
required_agent_role: <one of A8 AGENT_ROLES>
risk_level: <LOW | MEDIUM | HIGH | UNKNOWN>
acceptance_criteria:
  - <≤200 chars>
  - <…>
human_needed: <true | false>
human_needed_reason: <closed reason; "none" iff human_needed=false>
-->
```

Rules:

- Markers are HTML comments — invisible to readers.
- Each marker is **one** delegation entry.
- Every required field must be present and pass the closed-vocab
  check; otherwise the marker is dropped with a `validation_warning`.
- `delegation_id` must match `^[A-Za-z0-9_.-]+$` and be unique
  across all sources.
- The grammar is intentionally minimal: scalar `key: value` lines
  plus an `acceptance_criteria:` list of indented `- value` lines.
- Anything that does not parse cleanly under this grammar is
  rejected — no fuzzy fallback.

Use markers **sparingly**. Canonical roadmap docs must remain
human-readable. Markers are appropriate for high-level approved
delegation anchors — the precise textual unit of work the operator
wants the queue to track. Bulk decomposition belongs in the
sidecar seed.

## Sidecar seed (bulk decomposition, optional)

```
docs/development_work_queue/delegation_seed.jsonl
```

Strict JSONL: one JSON object per non-blank line. No `#` comments.
Empty by default. Each entry follows the same schema as the marker
fields. The `delegation_id` must be unique across the whole
delegation surface.

The sidecar is operator-authored. Promotion to the work queue
remains manual.

## Hard guarantees (pinned by tests)

- ADE core stdlib + `reporting.execution_authority` +
  `reporting.approval_policy` + `reporting.development_work_queue`.
- No subprocess, no network, no `gh`, no `git`.
- No imports from `dashboard`, `automation`, `broker`,
  `agent.risk`, `agent.execution`, `research`,
  `reporting.intelligent_routing` (AST-level pin).
- Atomic write only under
  `logs/development_delegation/latest.json`.
- Plain markdown headings / prose / lists / bullets produce zero
  delegation entries (load-bearing false-positive guard).
- Roadmap paths under `docs/roadmap/archive/**` are excluded by
  both inclusion list and a positive `archive/` substring check.
- Non-canonical roadmap paths are excluded even when explicitly
  passed.
- Wrapper carries an explicit `discipline_invariants` block:
  ```
  writes_to_seed_jsonl: false
  writes_to_bugfix_seed_jsonl: false
  writes_to_delegation_seed_jsonl: false
  fuzzy_parsing: false
  operator_promotion_required: true
  ```

## Output: per-entry schema

```
delegation_id                     deterministic, operator-authored
title                             bounded scalar
source_document                   canonical roadmap path or "delegation_seed"
source_section_or_anchor          "marker_<n>" or "line_<n>"
roadmap_track                     autonomous_development | qre_feature_build | sidecar_seed
category                          A8 CATEGORIES
required_agent_role               A8 AGENT_ROLES
supporting_agent_roles            list (empty in v0; reserved)
execution_authority_decision      from classifier
execution_authority_reason        from classifier
status                            "triaged" (default; operator promotes onward)
human_needed                      bool
human_needed_reason               A8 HUMAN_NEEDED_REASONS
risk_level                        from RISK_CLASSES
protected_surface                 true if target is canonical/protected/CI/etc.
acceptance_criteria               from marker
validation_requirements           list (empty in v0; reserved)
notes                             bounded scalar
created_at_placeholder            "deterministic_seed_placeholder"
updated_at_placeholder            "deterministic_seed_placeholder"
```

## Authority overrides

- A delegation entry in the autonomous_development or qre_feature_build
  track ⇒ classifier maps `source_document = canonical_roadmap` ⇒
  `execution_authority_decision = NEEDS_HUMAN`. The marker itself
  cannot be auto-allowed; operator-authored.
- Sidecar seed entries with `source_document = delegation_seed`
  classify under `target_path_category = other` ⇒ `NEEDS_HUMAN`
  (fail-safe). To be auto-allowed, the operator must edit the
  marker to point at a concrete repo path before promotion.
- Any entry with `human_needed=true` is unambiguously
  operator-gated.

## CLI surface

```
python -m reporting.development_delegation            # writes artifact
python -m reporting.development_delegation --no-write  # stdout only
```

## Modifying this document

Standard governance discipline. Scope-bounded PR, CI green,
post-merge gates, no `--admin` merge.
