# QRE Single Dataset Governed Offline Replay

This replay layer admits or blocks exactly one offline fixture/sample/cache
dataset boundary before routing one governed hypothesis through the existing
offline dry-run and artifact persistence contracts.

It records source provenance, data provenance, and a dataset fingerprint in the
persisted governed offline artifact. If the source is not approved or the data
is not admitted, the replay produces explicit canonical rejection reasons and a
blocked artifact instead of treating missing evidence as negative evidence.

The replay writes only to a caller-provided artifact directory. It does not
mutate `research/research_latest.json` or `research/strategy_matrix.csv`, run
production research, broaden datasets, generate production strategies, or grant
strategy synthesis, shadow, paper, live, broker, risk, order, or capital
authority.
