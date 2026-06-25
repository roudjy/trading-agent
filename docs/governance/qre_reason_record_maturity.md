# QRE Reason Record Maturity

- record_count: 45
- linked_record_count: 45
- invalid_record_count: 47
- durable_artifact_missing_count: 0
- audit_manifest_total: 0
- audit_coverage_pct: 98.94
- final_recommendation: reason_record_maturity_contract_gaps
- exact_next_action: normalize_reason_record_contract_gaps_before_authority_upgrade

## Durable Artifacts
| Artifact | Status | Size bytes |
| --- | --- | ---: |
| logs/qre_reason_records/latest.jsonl | present | 24126 |
| logs/qre_reason_records/latest.meta.json | present | 796 |
| logs/qre_reason_record_audit/latest.json | present | 11577 |
| logs/qre_reason_record_normalization/latest.json | present | 137352 |

## Audit Producers
| Producer | Status | With refs | Expected |
| --- | --- | ---: | ---: |
| real_basket_diagnosis | coverage_missing | 0 | 15 |
| routing_readiness_from_basket | coverage_missing | 0 | 15 |
| sampling_readiness_from_basket | coverage_missing | 0 | 15 |
| source_quality_readiness | coverage_complete | 4189 | 4189 |
| failure_action_mapping | no_subjects | 0 | 0 |
| paper_readiness_blockers | coverage_partial | 6 | 6 |

## Normalization Producers
| Producer | Status | Records | Invalid |
| --- | --- | ---: | ---: |
| qre_candidate_quality_framework | normalized_ready | 15 | 0 |
| qre_evidence_complete_basket_closure | normalized_with_contract_gaps | 1 | 1 |
| qre_reason_records_v1 | normalized_with_contract_gaps | 45 | 45 |
| qre_shadow_readiness_gates | normalized_with_contract_gaps | 1 | 1 |

## Contract Gap Counts
| Rejection reason | Count |
| --- | ---: |
| missing_consumer_refs | 47 |
| missing_required_fields | 2 |

## Linkage Examples
| Record family | Subject | Status | Missing paths |
| --- | --- | --- | --- |
| none | none | linked | - |

