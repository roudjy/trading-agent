# QRE Governed Offline Artifacts

This contract persists governed offline QRE dry-run outputs as versioned JSON
artifacts under a caller-provided safe artifact directory such as
`logs/qre_governed_offline_research/`.

The persistence layer is offline-only. It does not run market research, broaden
datasets, create production candidates, create production strategies, mutate
frozen outputs, or grant any trading authority.

## Envelope

Each artifact contains:

- schema version and report kind
- run id and UTC timestamp
- source mode and fixture fingerprint
- explicit authority denial statement
- input identifiers and provenance
- ordered canonical stage records
- evidence pack with missing, negative, governance, and data/source-quality
  blockers separated
- disposition and next action
- rejection reasons
- memory feedback
- operator trust summary

`latest.json` may be written only inside the caller-provided artifact
directory. The frozen outputs remain forbidden:

- `research/research_latest.json`
- `research/strategy_matrix.csv`
