# QRE Canonical Contract Vocabulary

## Purpose

This document settles the provider-agnostic QRE contract vocabulary for future bridge PRs. It does not implement a new research feature, create candidates, run screening, launch campaigns, validate strategies, promote candidates, or grant paper/shadow/live/trading authority.

The canonical metadata helper is:

```text
packages/qre_research/canonical_contracts.py
```

The helper is read-only schema metadata. It exists so the Tiingo research-only mini-loop, alpha discovery paths, run_research legacy outputs, and daily digest observability can be bridged to one shared vocabulary later.

## Architecture Position

The Tiingo research-only mini-loop is closed as a provider-specific mini-loop:

```text
hypothesis -> lifecycle -> candidate specs -> variants -> screening -> evidence ledger -> feedback -> next-run candidate feedback
```

The full provider-agnostic QRE loop is not yet proven closed:

```text
hypothesis generation
-> canonical CandidateSpec
-> StrategySpec / Strategy IR
-> PresetSpec
-> CampaignSpec
-> CampaignRun / ScreeningResult
-> EvidencePack / EvidenceLedger
-> FeedbackMemory / LessonMemory
-> next HypothesisBatch generation
```

## Provider Boundary

Provider-specific logic is allowed only in:

```text
provider adapters
source manifests
source snapshots
dataset fingerprints
provenance
```

Provider-specific logic is forbidden in:

```text
CandidateSpec semantics
StrategySpec semantics
PresetSpec semantics
CampaignSpec semantics
EvidencePack / evidence decision semantics
FeedbackRecord / feedback decision semantics
readiness or promotion policy
```

Daily digest remains observability-only. It may consume sidecars and summarize status, but it must not produce research objects.

Legacy outputs remain protected:

```text
research/research_latest.json
research/strategy_matrix.csv
```

## Vocabulary Table

| Contract | Purpose | Required fields | Optional fields | Producer | Consumer | Provider-specific fields allowed | Provenance fields | Current owner | Status | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| DataProvider | External or local data provider capability | provider_id, provider_kind, capabilities | adapter_module, license_scope, credential_requirement | provider_adapter | source_manifest | provider_id, adapter_module | none | packages/qre_data/contracts.py | inferred | DEFINE_CANONICAL_SCHEMA |
| SourceManifest | Source scope, license, and admissible use | source_id, provider_id, asset_scope, license_scope, quality_policy | adapter_version, credential_policy, refresh_policy | source_manifest | source_snapshot | source_id, provider_id | none | research/external_intelligence/source_manifest_schema.py | present | KEEP |
| SourceSnapshot | Immutable source state and lineage | source_snapshot_id, source_id, snapshot_time, lineage_refs | coverage, quality_flags, schema_refs | source_snapshot | observation_snapshot | source_snapshot_id, source_id | source_id, source_snapshot_id, lineage_refs | packages/qre_research/alpha_discovery/contracts.py | present | KEEP |
| DatasetFingerprint | Exact dataset content identity | dataset_fingerprint_id, source_snapshot_id, content_digest | row_count, coverage_window, partition_refs | dataset_fingerprint | observation_snapshot | source_snapshot_id | source_snapshot_id, partition_refs | ambiguous | inferred | DEFINE_CANONICAL_SCHEMA |
| ObservationSnapshot | Provider-neutral research observation context | observation_snapshot_id, dataset_fingerprint_id, diagnostics | regime_context, coverage_summary, research_memory_refs | research_observation | hypothesis_generation | none | dataset_fingerprint_id | packages/qre_research/alpha_discovery/contracts.py | present | BRIDGE |
| Hypothesis | Provider-neutral mechanism to falsify | hypothesis_id, mechanism, predicted_effect, falsification_conditions | confounders, supporting_observations, novelty_dimensions | hypothesis_generation | admission_boundary | none | observation_snapshot_id | ambiguous | ambiguous | OPERATOR_DECISION_REQUIRED |
| HypothesisSeed | Stable admitted seed identity | hypothesis_seed_id, source_hypothesis_id, source_snapshot_id | feature_family, source_hypothesis_digest | admission_boundary | research_input_contract | none | source_snapshot_id, source_hypothesis_digest | research/qre_tiingo_hypothesis_lifecycle.py | present | BRIDGE |
| ResearchInputContract | Admission-boundary candidate input | contract_id, hypothesis_seed_id, decision, required_candidate_spec_fields | allowed_candidate_families, forbidden_authorities | admission_boundary | candidate_materializer | none | hypothesis_seed_id, source_snapshot_id | research/qre_tiingo_candidate_research_loop.py | present | BRIDGE |
| CandidateSpec | Provider-neutral research candidate semantics | candidate_id, parent_contract_id, signal_definition, selection_rule | rebalance_rule, holding_period, benchmark, variant_parameters | candidate_materializer | strategy_spec_builder | none | parent_contract_id, source_snapshot_id | research/qre_tiingo_candidate_research_loop.py | present | GENERALIZE |
| StrategySpec | Provider-neutral strategy semantics | strategy_spec_id, candidate_id, signal_semantics, position_semantics | entry_semantics, exit_semantics, portfolio_semantics | strategy_spec_builder | preset_builder | none | candidate_id | ambiguous | ambiguous | OPERATOR_DECISION_REQUIRED |
| StrategyIR | Intermediate representation for strategy compilation | strategy_ir_id, strategy_spec_id, primitive_graph | compiler_version, safety_annotations | strategy_compiler | preset_builder | none | strategy_spec_id | packages/qre_research/alpha_discovery/strategy_ir.py | ambiguous | OPERATOR_DECISION_REQUIRED |
| PresetSpec | Provider-neutral runnable research preset | preset_id, strategy_spec_id, parameter_values, execution_tier | cost_model_ref, slippage_model_ref | preset_builder | campaign_planner | none | strategy_spec_id | ambiguous | ambiguous | OPERATOR_DECISION_REQUIRED |
| CampaignSpec | Provider-neutral bounded campaign plan | campaign_spec_id, preset_id, screening_protocol, evidence_requirements | budget, null_controls, stopping_rules | campaign_planner | campaign_runner | none | preset_id | ambiguous | ambiguous | OPERATOR_DECISION_REQUIRED |
| CampaignRun | Execution record for a bounded campaign | campaign_run_id, campaign_spec_id, run_status, artifact_refs | started_at, completed_at, resource_usage | campaign_runner | evidence_evaluator | none | campaign_spec_id | ambiguous | inferred | DEFINE_CANONICAL_SCHEMA |
| ScreeningResult | Provider-neutral screening metrics | screening_result_id, candidate_id, decision, metrics | null_control, blocked_reasons, decision_reasons | campaign_runner | evidence_evaluator | none | candidate_id, campaign_run_id | research/qre_tiingo_candidate_research_loop.py | present | GENERALIZE |
| EvidencePack | Provider-neutral evidence collection | evidence_pack_id, campaign_run_id, screening_result_refs, decision_basis | diagnostics_refs, ledger_refs | evidence_evaluator | disposition_policy | none | campaign_run_id | ambiguous | ambiguous | OPERATOR_DECISION_REQUIRED |
| EvidenceLedger | Research-only evidence index | evidence_id, evidence_kind, metrics_digest, evidence_decision | metrics_summary, null_control_summary, audit_flags | evidence_evaluator | disposition_policy | none | candidate_id, source_snapshot_id | research/qre_tiingo_candidate_research_loop.py | present | BRIDGE |
| Disposition | Provider-neutral research decision | disposition_id, evidence_pack_id, decision, reason_codes | next_actions, operator_notes | disposition_policy | feedback_memory | none | evidence_pack_id | ambiguous | inferred | DEFINE_CANONICAL_SCHEMA |
| FeedbackRecord | Next-run consumable feedback | feedback_id, subject_id, feedback_decision, next_action | feedback_reasons, consumable_by_next_run | feedback_memory | hypothesis_generation | none | subject_id, disposition_id | research/qre_tiingo_candidate_research_loop.py | present | BRIDGE |
| LessonMemory | Compressed research lesson | lesson_id, disposition_id, lesson_type, do_not_repeat | generator_constraints, recommended_next_question | feedback_memory | hypothesis_generation | none | disposition_id | packages/qre_research/alpha_discovery/contracts.py | ambiguous | OPERATOR_DECISION_REQUIRED |
| ResearchMemory | Store of prior outcomes and lessons | research_memory_id, lesson_refs, feedback_refs | terminal_outcomes, active_contradictions | feedback_memory | hypothesis_generation | none | memory_snapshot_id | ambiguous | ambiguous | OPERATOR_DECISION_REQUIRED |
| DailyDigestInput | Observability input from sidecars | digest_kind, source, counts, authority_summary | next_actions, status | research_sidecar | daily_digest | none | source, source_snapshot_id | research/qre_daily_status_digest.py | present | KEEP_AS_OBSERVABILITY |
| OperatorSummary | Human-readable read-only summary | summary_path, source_report_kind, status_lines | tables, warnings | observability | operator | none | source_report_kind | research/qre_daily_status_digest.py | present | KEEP_AS_OBSERVABILITY |
| RegistryEntry | Protected strategy registration entry | strategy_id, strategy_callable, enabled | metadata, eligibility | registry | run_research | none | registry.py | registry.py | present | KEEP |
| StrategyMatrixRow | Frozen legacy matrix row output | strategy_id, metric_columns, status | diagnostics, run_metadata | run_research | operator_report | none | research/strategy_matrix.csv | research/strategy_matrix.csv | present | KEEP_AS_LEGACY_OUTPUT_CONTRACT |

## Testable Boundaries

The vocabulary tests assert:

- all required canonical objects are present;
- provider-specific fields stop at adapter/source/snapshot/fingerprint/provenance layers;
- semantic contracts do not allow provider-specific fields;
- daily digest contracts are observability-only;
- `research/research_latest.json` and `research/strategy_matrix.csv` are not mutated by vocabulary validation;
- no contract grants broker, risk, order, validation, promotion, paper, shadow, live, or trading authority.

## Tiingo Bridge

The Tiingo provider-adapter bridge lives in:

```text
packages/qre_research/tiingo_canonical_bridge.py
```

It maps:

```text
Tiingo HypothesisSeed -> canonical Hypothesis
Tiingo ResearchInputContract -> canonical ResearchInputContract
Tiingo CandidateSpec -> canonical CandidateSpec
```

Bridge rules:

- Tiingo identifiers and source references are retained only in `provenance`.
- canonical Hypothesis and CandidateSpec semantics must not contain provider-specific terms;
- canonical IDs are deterministic and do not include provider names;
- missing required fields fail closed;
- unsafe authority flags fail closed;
- the bridge writes nothing and does not run screening.

Tiingo EvidenceLedger and FeedbackRecord bridging is intentionally left for the evidence/memory bridge PR.

## What This PR Does Not Build

This settlement does not create:

- Tiingo variants;
- daily digest cosmetics;
- campaign execution;
- validation or promotion;
- paper, shadow, or live paths;
- broker, risk, order, or capital allocation behavior;
- strategy synthesis or executable strategy code.

## Next Safe PR

```text
research: bridge Tiingo artifacts to canonical Hypothesis and CandidateSpec
```
