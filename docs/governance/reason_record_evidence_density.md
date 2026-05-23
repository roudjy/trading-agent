# Reason Record Evidence Density

> Status: ADE-QRE-014B read-only reporting sidecar.
>
> Module: `reporting.reason_record_evidence_density`.
>
> Scope: inspect reason-record and adjacent decision sidecars for
> operator-readable reasons and bounded evidence references. This sidecar does
> not append reason records, mutate campaigns, enable strategy synthesis, or
> touch frozen research outputs.

## Purpose

The trusted loop needs reason records that an operator can inspect without
reading source code. This reporter counts whether current reason surfaces have:

- structured `reason_codes`;
- bounded `reason_text`;
- explicit `evidence_refs`;
- an operator-readable summary.

Missing or empty evidence references fail closed with
`not_ready_missing_evidence_refs`. No record inventory fails closed with
`not_ready_no_reason_records`.

## Inputs

The reporter reads existing sidecars only:

- `logs/reason_records/*.jsonl`;
- `logs/intelligent_routing_minimal/latest.json`;
- `logs/sampling_intelligence_minimal/latest.json`;
- `logs/failure_action_mapping_minimal/latest.json`;
- `research/synthesis_gate_latest.v1.json` as reference-only synthesis-gate
  evidence.

The synthesis gate remains blocked/reference-only. The reporter does not call
or activate synthesis behavior.

## Output

Run:

```text
python -m reporting.reason_record_evidence_density --no-write
```

The optional write mode stores a deterministic sidecar under:

```text
logs/reason_record_evidence_density/latest.json
```

The output includes `baseline_without_sidecars` and `after_with_sidecars` so
operators can see the density lift provided by bounded sidecar evidence
references without changing the strict reason-record JSONL schema.
