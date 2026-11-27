"""One correlation id per request, in the service's log (GCP-02 Phase B, item 3)."""
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from o2c_agent_service import correlation


def test_the_callers_id_is_kept_logged_and_returned(caplog):
    app = FastAPI()
    correlation.install(app, "svc")

    @app.get("/thing")
    def thing():
        return {"ok": True}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        given = client.get("/thing", headers={"X-Correlation-Id": "run-42"})
        made = client.get("/thing")
    assert given.headers["X-Correlation-Id"] == "run-42" and made.headers["X-Correlation-Id"] not in ("", "run-42")
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "uvicorn.error"]
    assert lines[0] == {**lines[0], "event": "http_request", "service": "svc", "correlation_id": "run-42",
                        "path": "/thing", "status": 200}


def test_the_callers_id_is_sent_on_the_calls_to_settlement():
    """The id of the incoming request reaches settlement-service (GCP-02 Phase B, item 3)."""
    import httpx
    from o2c_agent_service.tools.services import settlement_tools
    seen = []

    def handler(request):
        seen.append(request.headers.get("X-Correlation-Id"))
        return httpx.Response(200, json={"status": "COMPLETED"})

    import asyncio
    tool = settlement_tools("http://settlement.test", transport=httpx.MockTransport(handler))["get_settlement"]
    asyncio.run(tool.execute({"settlement_id": "s-1"}, tenant_id="acme", correlation_id="run-42"))
    assert seen == ["run-42"]


def test_stock_is_topped_up_to_the_catalog_level_once_a_day():
    """The demonstration landscape buys goods on every scenario run: par-level restock, keyed by day."""
    from o2c_agent_service.services.stores import InventoryStore
    level = {"SKU-100": 50}
    inventory = InventoryStore(level)
    assert inventory.reserve("SKU-100", 48)
    assert inventory.available("SKU-100") == 2
    assert inventory.top_up(level, "2026-11-27") == {"SKU-100": 48}
    assert inventory.available("SKU-100") == 50
    assert inventory.reserve("SKU-100", 10)
    assert inventory.top_up(level, "2026-11-27") == {}          # the same day: nothing more is added
    assert inventory.available("SKU-100") == 40
    assert inventory.top_up(level, "2026-11-28") == {"SKU-100": 10}
