# Architecture Decision Records

One record per significant decision (context, options, decision, consequences). Records are not edited to change history: a reversed decision gets a new record that supersedes the old one. These are the decisions of `o2c-agent-service`. Platform-wide decisions (a real cloud rather than emulators only, synthetic data, Workload Identity Federation, promotion, the documentation layout) are in the [assistant repository's ADR index](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/adr/README.md).

Template: [`0000-template.md`](0000-template.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-one-e2a-workflow-declared-steps-with-one.md) | One E2A workflow of declared steps with one idempotency claim, replacing the spike's LangGraph state machine | Accepted |
| [0002](0002-order-is-created-as-reserving-before-anything.md) | An order is created as RESERVING before anything moves, with keyed stock and charge changes | Accepted |
| [0003](0003-stock-is-compare-set-counter-keyed-change.md) | Stock is a compare-and-set counter; a keyed change records its key in the same write | Accepted |
| [0004](0004-daily-par-level-restock-for-demonstration.md) | A daily par-level restock for the demonstration landscape, off by default | Accepted |
| [0005](0005-transactional-outbox-order-events-published-by.md) | A transactional outbox of order events, published by a leased sweeper, de-duplicated by consumers | Accepted |
| [0006](0006-approval-stage-before-any-reservation-or.md) | Approval stage before any reservation or charge; decided once by a finance approver who is not the requester | Accepted |
| [0007](0007-recover-unfinished-orders-schedule-recover.md) | Recover unfinished orders on a schedule (`recover_stuck`, every five minutes), never taking over a live claim | Accepted |
| [0008](0008-knowledge-answers-by-hybrid-retrieval-citing.md) | Knowledge answers by hybrid retrieval, citing and grounded | Accepted |
| [0009](0009-read-only-tools-over-mcp-scoped-caller-tenant.md) | Read-only tools over MCP, scoped to the caller's tenant | Accepted |
| [0010](0010-cloud-run-iam-with-google-id-token-service.md) | Cloud Run IAM with a Google ID token; service-to-service tokens exchanged where needed | Accepted |
| [0011](0011-admission-control-at-20-requests-flight.md) | Admission control at 20 requests in flight | Accepted |
