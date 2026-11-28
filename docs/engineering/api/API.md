# API reference

Source: `o2c-agent-service/src/o2c_agent_service/`. On Cloud Run the service is private and IAM verifies the caller's Google ID token.

| Method and path | Purpose | Responses |
|---|---|---|
| `POST /api/v1/assistant` `{"text": "..."}`, optional `Idempotency-Key` | natural-language front door: place an order, ask its status, payment exceptions, policy questions | 200 `AssistantResponse` with `status` COMPLETED, AWAITING_APPROVAL, NEEDS_CLARIFICATION, REFUSED, REPLAYED, CONFLICT, IN_PROGRESS, RECOVERY_REQUIRED, FAILED_FINAL or FAILED · 400 · 401/403 · 503 admission control |
| `GET /api/v1/approvals?status=` | the tenant's approvals | 200 |
| `POST /api/v1/approvals/{id}/approve`, `/reject` | decide an approval | 200 the resumed order or the rejection · 403 wrong role, own order or already decided · 404 |
| `GET /api/v1/orders/{id}` | one order | 200 · 404 |
| `POST /api/v1/orders/{id}/recover` | finish an unfinished order | 200 the order after recovery · 404 |
| `GET /api/v1/usage` | simulated model calls, tokens and cost | 200 (no caller check in the service, G-8) |
| `POST /mcp` | JSON-RPC 2.0: `check_stock`, `get_order` (read-only, tenant-scoped) | 200 |
| `POST /internal/events/publish` | sweep the outbox to Pub/Sub | `{status, published, failed_keys}`; `SKIPPED_LOCKED` when another sweeper holds the lease |
| `POST /internal/orders/recover` | the scheduled sweep of unfinished orders | `{checked, finished, still_open, removed}` |
| `GET /health` | liveness | `{status: UP}` |

Guarantees: an order executes once per key; a customer is charged once per order; stock never goes below zero; nothing is reserved or charged before a required approval. Every response carries `X-Correlation-Id`; the service forwards it on calls to settlement and reconciliation.
