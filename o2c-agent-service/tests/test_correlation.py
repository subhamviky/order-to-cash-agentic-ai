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
