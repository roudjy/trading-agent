---
description: Decompose a roadmap item into an ordered task plan via the planner agent.
allowed-tools: [Agent]
---

# /plan-roadmap-item

Use this command to begin work on a roadmap item. The flow:

1. The planner agent reads
   docs/roadmap/v3.15.15.12-agent-governance.md (or the named version
   doc) plus the relevant ADRs and produces
   docs/governance/plan_<task>.md.
2. The architecture-guardian reviews the plan and either approves or
   returns required revisions.
3. The operator manually approves the plan.
4. Only then is /plan-roadmap-item complete; subsequent work flows to
   the appropriate write-capable agent (implementation, test, frontend,
   observability) under the planner's scope.

This command never writes outside docs/governance/plan_*.md and
docs/governance/agent_run_summaries/.

Arguments: $ARGUMENTS - a free-text roadmap item or section reference.
