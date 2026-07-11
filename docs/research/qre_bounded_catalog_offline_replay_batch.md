# QRE Bounded Catalog Offline Replay Batch

The bounded catalog offline replay batch runs a small caller-provided plan of
dataset/hypothesis pairs through the offline dataset catalog, governed offline
runner, and governed offline run registry.

The batch enforces run budgets, per-dataset budgets, per-hypothesis budgets,
duplicate run suppression, and do-not-retest suppression. It writes artifacts
and the run registry only under the caller-provided output directory.

This is governed offline research only. It does not fetch external data, create
production strategies or campaigns, mutate frozen outputs, or grant synthesis,
shadow, paper, live, broker, risk, order, or capital authority.
