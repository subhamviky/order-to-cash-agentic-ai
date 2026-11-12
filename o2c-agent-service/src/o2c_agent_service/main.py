"""o2c-agent-service - FastAPI entry point (scaffolded by P0)."""
import logging

from fastapi import FastAPI

logger = logging.getLogger("o2c_agent_service")

app = FastAPI(title="o2c-agent-service")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by the container HEALTHCHECK and the platform."""
    return {"status": "UP", "service": "o2c-agent-service"}
