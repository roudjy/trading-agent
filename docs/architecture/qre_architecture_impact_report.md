# QRE Architecture Impact Report

`tools/qre_architecture_impact_report.py` is a read-only static reporter for
QRE architecture changes. It summarizes which registry, maturity, authority,
and protected-output surfaces are touched by a working-tree diff or by an
explicit base/head diff.

The command does not run research, create candidates, create strategies, run
screening, mutate frozen outputs, or grant strategy, shadow, paper, live,
broker, risk, order, or capital authority.

## Usage

```powershell
python tools/qre_architecture_impact_report.py
python tools/qre_architecture_impact_report.py --base origin/main --head HEAD
python tools/qre_architecture_impact_report.py --json
```

## Report Fields

- `changed_qre_files`: changed files inside QRE architecture-relevant paths.
- `new_producer_modules`: changed QRE Python modules not registered as
  producers.
- `new_consumer_modules`: changed QRE Python modules that import QRE surfaces
  without existing consumer registration.
- `new_artifact_paths`: artifact paths referenced by changed files that are not
  covered by the architecture registry.
- `canonical_objects_touched`: canonical object names found in changed paths or
  changed file text.
- `registry_entries_touched`: registry entry IDs matched by changed paths,
  artifact paths, or explicit entry ID references.
- `maturity_claims_touched`: maturity labels or Addendum 4 evidence
  requirements found in changed paths or text.
- `authority_flags_touched`: authority flags found in changed paths or text.
- `protected_outputs_touched`: frozen legacy outputs touched directly or
  referenced by changed files.
- `operator_decision_required`: registry entries or change classes that require
  operator review.
- `verdict`: `safe`, `review_required`, or `blocked`.
- `recommended_next_action`: the next governance action implied by the verdict.

## Verdicts

`safe` means the diff does not appear to touch QRE architecture surfaces.

`review_required` means the diff touches registry entries, maturity labels,
authority flags, new QRE producers, or new artifact paths. The change should
update registry or maturity coverage and run the static QRE gates before merge.

`blocked` means the diff touches protected outputs or blocked authority flags.
The change must stop for operator review before merge.

The report is advisory for PR review. It is intentionally static and does not
replace the closed-world architecture audit gate.
