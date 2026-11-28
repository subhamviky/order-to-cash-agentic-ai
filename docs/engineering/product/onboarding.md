# Onboarding

Read: `README.md`, the [solution overview](solution-overview.md), the design document sections 4, 8 and 10, [ADRs](../adr/README.md) 1, 2, 3, 6.

Run locally:

```bash
cd o2c-agent-service && poetry install && poetry run pytest -q      # settlement and reconciliation are in-process fakes
```

Map: `src/o2c_agent_service/` (`workflow`, `agents`, `services/stores.py` with `InventoryStore`, `services/assistant.py`, governance, tools, the MCP server), `policies/` (catalog and governance), `o2c-agent-service/infra` (Terraform).

Working agreements: one concern per branch; CI green to merge; a regression test for every bug (for example `test_order_recovery.py`); an ADR for decisions worth explaining; never real data; deploys and the scenario run through workflows in the assistant repository ([release process](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/release-process.md)). Know before you run the scenario: stock is finite and tops up once per UTC day.
