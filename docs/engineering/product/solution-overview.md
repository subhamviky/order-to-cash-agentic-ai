# Solution overview

*One page. Synthetic data, one author.*

**The problem.** Sales and finance talk about orders, payments and policies in plain language, but every material action (reserve stock, charge, approve) must be governed, exactly-once and recoverable.

**What it is.** The natural-language front door of an order-to-cash landscape. A workflow routes the request, parses an order, checks credit, asks for approval when the amount requires it, reserves stock, charges through the settlement ledger, and publishes order events; unfinished orders recover themselves; finance and policy questions are answered from facts and cited sources; read-only tools are available to other agents over MCP. It runs on Google Cloud's free tier.

**Evidence.** The cloud scenario passes (orders paid, the audit flag, the short payment); a crash anywhere in the order saga is recoverable with the same keys (`test_order_recovery.py` on the emulators); the stock exhaustion found by a drill became a documented, tested restock. Design: `docs/design/`; decisions: [ADRs](../adr/README.md).

**Limits.** Single-tenant catalog; the model is simulated by default; the internal routes rely on IAM, not a role check; a claim with no order cannot be recovered (minor); no load test.
