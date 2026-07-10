# QRE Rejection Reason Intelligence

`packages/qre_research/rejection_reasons.py` defines provider-agnostic,
machine-readable reason codes for blocked or rejected QRE funnel states.

The taxonomy separates missing evidence from negative evidence and makes
architecture, maturity, policy, and operator-decision failures visible as
governance rejections.

Each `ReasonRecord` carries:

- canonical reason code;
- funnel stage;
- object id;
- severity;
- human-readable explanation;
- next action;
- evidence polarity;
- terminal/intermediate status.

Reason records can be serialized into `FeedbackRecord`, `LessonMemory`, and
`ResearchMemory` read-model payloads. They do not run research, create
candidates, create strategies, create campaigns, mutate frozen outputs, or grant
strategy synthesis, shadow, paper, live, broker, risk, order, or capital
authority.
