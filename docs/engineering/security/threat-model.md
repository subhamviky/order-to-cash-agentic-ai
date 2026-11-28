# Threat model: o2c-agent-service

- **Status:** Reviewed 2026-11-28 · STRIDE · platform model and residual risks: [assistant repository](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/security/threat-model.md). Synthetic data only.

**Assets:** orders, stock, approvals, the customers' credit limits, order events, the ability to charge through settlement-service.

| # | Threat | Control | Evidence |
|---|---|---|---|
| O1 | **Spoofing** a caller or tenant | Cloud Run IAM verifies the ID token; `Caller` from verified claims; tenant pattern `^[a-z][a-z0-9-]{1,31}$` | design 5.6 |
| O2 | **Tampering**: an order executed twice or a customer charged twice | E2A claim with a business-content fingerprint; settlement `Idempotency-Key` = order id (also on recovery) | I-1, I-2 |
| O3 | **Tampering**: oversold stock or double reserve | compare-and-set stock; keyed changes recorded in the same write | I-3 |
| O4 | **Tampering**: reserve or charge before a required approval | `ApprovalStage` before `_act` | I-5 |
| O5 | **Tampering**: prompt injection through the request or retrieved text | firewall stage; router and intake outputs validated; the finance agent refuses any id, amount or status not in the facts; the knowledge agent must cite what it retrieved | governance stages, tests |
| O6 | **Repudiation** | approvals record requester and decider; an order change and its event commit together | I-6, I-7 |
| O7 | **Information disclosure**: cross-tenant read | stores filter by tenant; MCP adds the caller's tenant | I-8 |
| O8 | **Denial of service**: a burst | capacity stage: over 20 in flight is 503 | ADR 0011 |
| O9 | **Elevation**: MCP used to write | only `check_stock` and `get_order`, read-only | ADR 0009 |
| O10 | **Elevation**: unauthenticated internal routes | `/internal/*` and `/api/v1/usage` have no caller check in the service; only direct Cloud Run invokers reach them (G-8) | residual |

Residual: G-8 and G-9 (ingress `INGRESS_TRAFFIC_ALL`, protected by IAM); the Secret Manager secret from the scaffold is not read (G-6); single-tenant catalog (G-5); a model that is simulated by default; no penetration test.
