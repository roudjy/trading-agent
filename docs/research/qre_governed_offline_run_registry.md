# QRE Governed Offline Run Registry

The governed offline run registry is a caller-directed lineage index over
governed offline artifact files. It records run id, artifact reference,
hypothesis id, dataset fingerprint, source mode, evidence completeness,
disposition, memory summary, do-not-retest values, and further-offline-research
eligibility.

The registry is a read model. Fixture and sample runs are explicitly marked as
not production empirical evidence. The registry writes only to caller-provided
safe directories and never mutates `research/research_latest.json` or
`research/strategy_matrix.csv`.
