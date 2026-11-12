"""o2c-agent-service - FastAPI entry point (scaffolded by P0, extended by hand)."""
import logging
import os
from pathlib import Path

from fastapi import FastAPI

from .routers.assistant import router as assistant_router
from .services.assistant import O2CAssistant
from .services.llm import build_o2c_llm

logger = logging.getLogger("o2c_agent_service")

SERVICE_ROOT = Path(os.getenv("SERVICE_ROOT", Path(__file__).resolve().parents[2]))


def build_app(assistant: O2CAssistant) -> FastAPI:
    app = FastAPI(title="o2c-agent-service")
    app.state.assistant = assistant
    app.include_router(assistant_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by the container HEALTHCHECK and the platform."""
        return {"status": "UP", "service": "o2c-agent-service"}

    return app


app = build_app(O2CAssistant(
    SERVICE_ROOT, build_o2c_llm(),
    settlement_url=os.getenv("SETTLEMENT_API_URL", "http://localhost:8080"),
    reconciliation_url=os.getenv("RECONCILIATION_API_URL", "http://localhost:8001")))
