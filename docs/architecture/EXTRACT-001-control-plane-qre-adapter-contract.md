# EXTRACT-001 - Control-Plane/QRE Adapter Contract Package

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/ARCH-005-adapter-contract-scaffold.md`
- `docs/architecture/ARCH-006-package-extraction-readiness-decision.md`
- `reporting/control_plane_qre_adapter_contract.py`
- `reporting/architecture_import_scan.py`

## 1. Purpose and Scope

EXTRACT-001 performs the first physical package extraction slice selected by
ARCH-006. The slice is deliberately narrow: only the control-plane/QRE read-only
adapter contract scaffold moves into a dedicated package namespace.

This unit does not migrate dashboard routes, move QRE read models, change
runtime behavior, update frozen outputs, or touch live, paper, shadow, risk,
broker, or execution behavior.

## 2. Canonical Namespace

The canonical adapter contract now lives at:

```text
packages/control_plane_qre_adapter_contract/
```

The package is classified by the architecture import scanner as
`adapter-contract`. It is not QRE runtime, dashboard/control-plane runtime,
execution, or ADE authority.

The canonical package remains stdlib-only and exposes the stable ARCH-005
contract surface:

- `ControlPlaneQREReadAdapter`
- `ReadModelContract`
- `AdapterContractDescription`
- `describe_contract()`
- `list_read_models`
- `read_json`
- `describe_contract`

## 3. Compatibility Import

The legacy reporting path remains importable:

```text
reporting/control_plane_qre_adapter_contract.py
```

It is now a small compatibility shim that re-exports the canonical package
objects. Existing tests and consumers using the reporting import path continue
to receive the same public contract objects.

## 4. Scanner and Boundary Status

The scanner has an explicit `adapter-contract` classification for the extracted
package. This keeps the package visible in architecture summaries without
classifying it as QRE, control-plane, execution, or ADE authority.

The extraction does not add control-plane-to-QRE imports. Existing exact
legacy/report-only findings remain visible; no wildcard allowlist is added.

## 5. Frozen and Protected Paths

Frozen outputs remain unchanged:

- `research_latest.json`
- `strategy_matrix.csv`

Protected behavior paths remain untouched:

- `.claude/**`
- live/paper/shadow/risk/broker/execution behavior

No dashboard mutation routes or runtime dashboard wiring are added.

## 6. Recommended Next Action

Recommended next action: continue with the next explicitly selected extraction
item only after EXTRACT-001 validation and CI complete successfully.
