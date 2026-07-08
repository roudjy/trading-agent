# QRE Funnel Architecture Audit

## Purpose

This document records the static architecture audit for QRE research funnels. The audit answers what exists today, which modules produce and consume artifacts, where provider-specific assumptions appear, and which paths should be kept, bridged, deprecated, or treated as observability-only.

## Audit Scope

The audit is static and behavior-preserving. It does not run research, create candidates, launch campaigns, validate strategies, register strategies, or touch paper/shadow/live paths.

The audit tool is:

```text
tools/qre_funnel_architecture_audit.py
```

Default mode prints JSON and writes nothing:

```powershell
python tools/qre_funnel_architecture_audit.py
```

Write mode writes only:

```text
logs/qre_funnel_architecture_audit/
```

## Initial Architectural Finding

The repo contains multiple partial funnels rather than one proven, provider-agnostic canonical loop:

- Tiingo hypothesis and candidate research mini-loop
- daily digest observability funnel
- run_research / registry / strategy_matrix funnel
- alpha discovery / campaign / evidence / memory style modules
- test and smoke fixture paths that may resemble funnel semantics

The Tiingo path is useful and should be kept, but it is provider-specific and should be bridged to canonical contracts before being treated as the general QRE architecture.

## Classification Settlement

PR F adds a read-only funnel classification registry:

```text
packages/qre_research/funnel_classification.py
```

The registry records:

- one canonical provider-agnostic contract/bridge/memory loop at the contract level
- Tiingo as a provider adapter bridged to canonical contracts
- daily digest as observability-only
- `research/research_latest.json` and `research/strategy_matrix.csv` as protected legacy output contracts
- smoke and fixture paths as fixture-only
- ambiguous alpha discovery / Strategy IR / campaign / lesson ownership as requiring bridge or operator decision

The classification registry does not execute research, create candidates, create strategies, launch campaigns, run screening, validate, promote, register strategies, or grant paper/shadow/live/trading authority.

The full runtime architecture still remains bounded by the no-execution safety rules. The settlement is a contract/bridge/memory/funnel-classification reconciliation, not a production trading readiness claim.

## Outputs

Write mode emits:

```text
logs/qre_funnel_architecture_audit/latest.json
logs/qre_funnel_architecture_audit/dependency_graph.json
logs/qre_funnel_architecture_audit/provider_leakage_report.json
logs/qre_funnel_architecture_audit/contract_map.json
logs/qre_funnel_architecture_audit/funnel_inventory.json
logs/qre_funnel_architecture_audit/operator_summary.md
```

Generated logs are not committed.

## Safety

This audit is architecture diagnosis only:

```text
audit_only=true
runtime_behavior_changed=false
created_candidates=false
created_strategies=false
created_presets=false
created_campaigns=false
ran_screening=false
trading_authority=false
validation_authority=false
paper_authority=false
shadow_authority=false
live_authority=false
```

