# Test strategy: o2c-agent-service

Shared principles: [platform strategy](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/testing/test-strategy.md). Layers (77 test functions):

| Layer | What it proves |
|---|---|
| Unit and agents | router, intake, execution, finance and knowledge agents' accept/fallback rules; the governance stages in order; entitlement; validation |
| Workflow and journeys | place an order, with and without approval; status; payment exceptions; policy questions; the claim and fingerprint (same key, same content replays; different content conflicts) |
| Recovery | `test_order_recovery.py`: crashes at each point of the saga on memory and on the emulators; keyed effects happen once |
| Concurrency | two orders for the last stock; two approvers at once; two sweeps at once (the lease) |
| Firestore and Pub/Sub emulators | the whole suite again with the real state and event bindings, several instances on one database |
| Release gate | E2A `ProjectReleaseGate`, seven stages |
| Container | the image is built, run, and asked a policy question |
| Infrastructure | Terraform fmt, validate, test with a mock provider |
| Cloud | the landscape scenario (orders paid, refused for stock, the audit flag) and the drills in the assistant repository |

Gaps: no load test; the managed-model profile is exercised only on the simulated model in CI; `G-12` (claim with no order) is a known untested gap.
