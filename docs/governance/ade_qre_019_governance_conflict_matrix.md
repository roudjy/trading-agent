# ADE-QRE-019 Governance Conflict Matrix

## Purpose

This document records the canonical-rule conflicts that blocked automated
research-only executable strategy generation before ADE-QRE-019 and the narrow
replacement rules admitted by the operator-authorized governance migration.

It is a migration aid and audit surface. It does not itself grant trading,
paper, shadow, broker, risk, or live authority.

## Conflict Matrix

| Source file | Previous rule | Conflict with ADE-QRE-019 | Replacement rule | Affected tests / classifiers |
| --- | --- | --- | --- | --- |
| `AGENTS.md` | "Do not let Codex invent strategies." | Blocked bounded deterministic compilation of approved theses into research-only executable strategies. | Codex may not invent unconstrained or discretionary strategies, but may deterministically compile an approved, complete Behavior Thesis through the ADE-QRE-019 typed-specification, template-generation, safety-gate, sandbox-validation, generated-registry admission, and canonical resolved research-only catalog pipeline. | Governance consistency tests; strategy-generation policy tests. |
| `docs/governance/no_touch_paths.md` | Full `research/**` write deny and categorical no-touch treatment for research authority surfaces. | Direct research-side generation and registration edits would violate the live hook and path doctrine. | `research/**` remains categorically protected. ADE-QRE-019 must use isolated generated-research surfaces outside `research/**`, then feed a single canonical resolver that composes protected manual authority with validated generated inputs. Frozen evidence outputs remain protected. | Protected-path scope tests; no-touch documentation tests. |
| `docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md` | Strategy synthesis blocked; no executable strategy generation. | Prevented the canonical roadmap from admitting the automated research-only generation lane. | Historical ADE-QRE-017 remains complete as written; later ADE-QRE-019 supersedes the categorical prohibition with a bounded research-only automated generation program. Deployment, paper, shadow, and live authority remain forbidden. | Queue and roadmap consistency tests. |
| `docs/roadmap/qre_campaign_lineage_evidence_remediation_program.md` | ADE-QRE-018 may not implement strategy synthesis, executable code generation, or automatic registration. | Prevented the queue from advancing from remediation into the next authorized program. | ADE-QRE-018 remains historically accurate and complete for remediation; ADE-QRE-019 becomes the first authorized implementation program for bounded automated research-only generation after ADE-QRE-018. | Queue audit and next-unit tests. |
| `docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md` | Strategy synthesis and automatic registration remained blocked after ADE-QRE-018. | Prevented canonical queue admission of ADE-QRE-019. | ADE-QRE-019 is admitted as the next authorized program, with explicit research-only generation, registration, preset, null-control, lineage, and portfolio readiness scope. | Queue self-audit; roadmap next-unit logic. |
| `research/qre_behavior_thesis_registry.py` | Thesis authority always forbade executable generation and strategy registration. | Direct mutation would violate the preserved `research/**` no-touch boundary. | ADE-QRE-019 does **not** rewrite this protected thesis surface. Generated-strategy admission is expressed in isolated generated-research artifacts plus a canonical resolver outside `research/**`, while the thesis registry remains bounded compiler input and historical context. | Generation-eligibility tests; resolver tests; protected-path scope tests. |

## Remaining Permanent Safety Boundaries

The following remain unchanged and are not relaxed by ADE-QRE-019:

- no live trading
- no broker orders
- no real capital
- no credential exposure
- no force push
- no admin merge
- no hook bypass
- no test weakening
- no arbitrary network access from generated strategies
- no arbitrary file-system access from generated strategies
- no `eval` or `exec`
- no subprocess execution from generated strategies
- no dynamic package installation
- no risk-control weakening

## Consistency Notes

- ADE-QRE-019 authorizes deterministic research-only generation and automatic
  generated-registry admission plus canonical resolved-catalog inclusion after
  all automated gates pass.
- ADE-QRE-019 does **not** authorize campaign execution, candidate promotion,
  paper, shadow, live, broker, risk, or deployment authority.
- ADE-QRE-019 does **not** require any `.claude/**` change and does **not**
  relax the live `research/**` deny hook.
- Historical documents may retain older blocked-language only when they are
  explicitly treated as superseded by this migration or by the ADE-QRE-019
  queue admission record.
