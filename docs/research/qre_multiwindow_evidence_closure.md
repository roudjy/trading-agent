# QRE Multi-Window Evidence Closure

Multi-window evidence closure records a bounded set of governed offline
evidence windows for a single-dataset replay:

- `in_sample`
- `out_of_sample`
- `null_model`
- `cost_model`
- `trade_count`
- `data_quality`

Each window is marked as `missing`, `failed`, `passed`, or `not_applicable`.
Missing windows remain missing evidence. Failed null/cost/data-quality windows
are negative evidence, while insufficient trades remains a missing-evidence
blocker until the data is sufficient.

The closure persists by updating a governed offline artifact envelope under the
caller-provided artifact directory. It does not broaden datasets, run production
research, mutate frozen outputs, or grant synthesis, shadow, paper, live,
broker, risk, order, or capital authority.
