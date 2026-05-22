# CI Path-Aware Gates

## Purpose

CI-001 introduces deterministic changed-path classification so the repository
can avoid unrelated expensive validation without weakening safety gates. The
classifier is `scripts/ci_path_classifier.py`; it emits coarse booleans for
workflow decisions and has unit coverage in `tests/unit/test_ci_path_classifier.py`.

## Always-On Checks

The fast pre-merge gate still runs these checks for every pull request and
main push:

- `path-classifier`.
- `secret-scan (gitleaks)`.
- `governance-lint`.
- `architecture-boundary`.
- `lint (ruff)`.
- `typecheck (mypy narrow)`.
- `unit (smoke + unit)`.
- `regression-fast (determinism pins)`.
- `hook-tests (governance hooks)`.

These jobs are not path-skipped by CI-001. This preserves the existing
branch-protection check names and keeps governance, hook, smoke, and
determinism coverage active on every PR.

## Path-Aware Checks

The classifier reports at least these categories:

- `docs_only`
- `architecture_only`
- `frontend`
- `dashboard_or_control_plane`
- `ade_governance_or_reporting`
- `qre_research`
- `packages`
- `tests`
- `ci_or_governance`
- `execution_sensitive`

The `frontend (vitest)` job runs only when changed paths touch frontend,
dashboard/control-plane, CI/governance, or execution-sensitive surfaces. Plain
docs-only, architecture-only, and package-contract-only changes avoid unrelated
Vitest execution.

## Deployment Gating

`Build & Push Docker Image` and `Deploy VPS Dashboard` still trigger only after
`Fast pre-merge gate` succeeds on `main`, or by explicit `workflow_dispatch`.
For automatic `workflow_run` events, each workflow classifies the merge commit
and proceeds only for deployment-relevant paths:

- frontend paths;
- dashboard/control-plane paths;
- packages;
- CI/governance paths;
- execution-sensitive paths;
- Docker/deploy/runtime configuration files.

Docs-only and architecture-only changes safely skip image build and VPS deploy.
Manual dispatch remains an operator-controlled override and is not path-skipped.

## Safety Non-Regression Rules

- Do not remove secret scanning.
- Do not remove governance lint.
- Do not remove hook tests.
- Do not remove smoke/unit or regression-fast determinism checks.
- Do not remove architecture boundary enforcement.
- Do not change frozen contracts to make a path gate pass.
- Do not use path gating to skip tests for changed code just because they are
  slow.
- Preserve existing required check names unless branch protection is updated by
  an operator-controlled governance change.

## Interpreting Skipped Jobs

A skipped path-aware job means the classifier found no relevant changed path for
that job. It does not mean the PR skipped safety validation: always-on checks
must still pass. If a reviewer believes a skipped job should have run, treat the
classifier rule as the defect and update it with a focused test.

## Rollback Plan

Revert the CI-001 workflow and classifier changes in one PR. The rollback
returns frontend, Docker build, and dashboard deploy behavior to unconditional
execution after the fast gate. Always-on checks require no rollback because they
were not made conditional.

## Known Limitations

- Classification is path-based. It does not inspect imports or runtime call
  graphs.
- Automatic Docker/deploy gating compares the merge commit against its first
  parent, which is appropriate for the repository's squash-merge lifecycle.
- Package changes remain deployment-relevant because packages can be included in
  built images.
