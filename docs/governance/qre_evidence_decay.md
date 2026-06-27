# QRE Evidence Decay

`reporting.qre_evidence_decay` materializes read-only decay semantics over
QRE thesis lineage, contradiction/staleness visibility, validation results,
and OOS evidence state.

The report is fail-closed. Stale, contradicted, incomplete, unreproducible,
or non-renewed evidence may not silently support readiness.

Current dimension coverage:

- source freshness
- data age
- campaign age
- reproducibility
- contradiction state
- source-authority loss
- superseded evidence
- regime relevance
- incomplete lineage
- missing OOS renewal

The output is context only. It does not authorize execution, candidate
promotion, campaign launch, paper/shadow/live activation, or any mutation of
frozen contracts.
