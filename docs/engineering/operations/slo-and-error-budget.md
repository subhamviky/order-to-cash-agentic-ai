# SLOs: o2c-agent-service

Defined once for the platform in [the assistant repository](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/slo-and-error-budget.md). Here: availability 99% of requests not 5xx over 28 days, with a fast-burn alert; no latency objective (a model is in the path). Admission control returns 503 above 20 requests in flight, which counts against availability by design: a sustained burst of 503s is a capacity signal, not a bug.

Signals worth watching (not objectives): orders stuck in RESERVING or PENDING_PAYMENT longer than the recovery threshold, and stock per SKU (see the incident response page).
