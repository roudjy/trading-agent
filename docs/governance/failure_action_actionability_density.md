# Failure-Action Actionability Density

> Status: ADE-QRE-014H implementation note.
>
> Runtime authority: read-only reporting. This note does not activate strategy
> synthesis, routing mutation, campaign mutation, dashboard mutation routes,
> approval mutation, Addendum runtime behavior, or paper/shadow/live execution.

`reporting.failure_action_mapping_minimal` measures actionability density over
existing failure-action mappings only. It does not infer causes, run research,
generate strategies, or mutate any queue.

## Density Rule

A mapping is actionable only when all of the following are true:

- the failure code is already in the closed failure taxonomy;
- the recommended action is already in the bounded action vocabulary;
- `evidence_count` is at least
  `MIN_EVIDENCE_FOR_RESEARCH_ACTION`;
- the recommendation is not `hold_no_action`;
- the recommendation is not `preserve_negative_result`.

The density is:

```text
actionability_density = actionable_mappings / total_mappings
```

When there are no mappings, density is `null` and the report fails closed.

## Non-Actionable Reasons

Non-actionable mappings remain explicit under
`counts.non_actionable_by_reason` and each item carries an
`actionability.reason_codes` list.

Closed non-actionable reasons:

- `insufficient_evidence`
- `hold_action`
- `negative_result_preservation`

These reasons are derived only from existing input fields and the closed mapping
policy. They are not root-cause claims.

## Operator Output

The report emits:

- per-item `actionability` status and operator explanation;
- aggregate `counts.actionable_recommendations`;
- aggregate `counts.non_actionable_recommendations`;
- aggregate `actionability.actionability_density`;
- aggregate `actionability.operator_summary`.

`safe_to_execute` remains `false` and `mode` remains `dry-run`.
