# Incident response: o2c-agent-service

Severity, roles and first steps: [platform page](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/incident-response.md). Symptoms specific here:

| Symptom | Likely cause | Check | Action |
|---|---|---|---|
| Orders come back REFUSED, "insufficient stock" | the seeded stock is used up and the day's top-up is spent | the order status and reason; `check_stock` over MCP | wait for 00:00 UTC, then force a new revision (the restock runs on its first start); see platform review 0002 and 0008 |
| `RECOVERY_REQUIRED` for a repeated order | the first attempt crashed inside the saga | the order id in the answer | `POST /api/v1/orders/{id}/recover`, or wait for the five-minute sweep |
| An order stuck in RESERVING or PENDING_PAYMENT | a crash; the sweep has not run yet | `open-orders` older than `O2C_RECOVERY_AFTER_SECONDS` | `POST /internal/orders/recover` |
| `PAYMENT_UNKNOWN` | settlement-service timed out or answered 409 | settlement health; the ledger for the order id | recovery re-reads with the same key; do not re-charge by hand |
| 503 from the API | more than 20 in flight | request rate | retry later; reduce concurrency |
| Events not appearing in Pub/Sub | the sweeper is not running or the lease is held | `POST /internal/events/publish` result (`SKIPPED_LOCKED`) | wait or trigger once |
| Approval 403 | own order, wrong role, or already decided | the approval record | a different finance approver |
