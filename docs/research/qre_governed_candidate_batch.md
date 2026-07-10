# QRE Governed Candidate Batch

The governed candidate batch plans a bounded set of offline candidates through
existing QRE throughput controls and runs the governed offline dry run only for
admitted candidates.

## Outputs

- batch plan
- admitted candidates
- blocked candidates with canonical reason codes
- offline dry-run results
- evidence/disposition summaries
- memory feedback records
- next-action queue

## Boundaries

The batch is deterministic and in-memory. It does not run uncontrolled
research, create production artifacts, mutate frozen outputs, or grant
strategy synthesis, shadow, paper, live, broker, risk, order, or capital
authority.
