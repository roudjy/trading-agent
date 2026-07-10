# QRE Hypothesis Generator Governance

`packages/qre_research/hypothesis_generator_governance.py` governs hypothesis
prioritization before throughput changes.

It considers:

- ResearchMemory and LessonMemory via rejection reason records;
- failure history and repeated reason codes;
- source identity and data quality;
- duplicate suppression;
- candidate budget constraints;
- operator-decision, architecture, and maturity gates.

The module emits auditable prioritization records with decision, reason codes,
rationale, score, and next action.

This PR does not increase throughput, run research, create production
candidates, create strategies, create campaigns, mutate frozen outputs, or grant
strategy synthesis, shadow, paper, live, broker, risk, order, or capital
authority.
