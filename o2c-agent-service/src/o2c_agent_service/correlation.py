"""One correlation id per request, in every service's log (GCP-02 Phase B, item 3).

The caller's X-Correlation-Id is kept (or one is made), logged on one JSON line per request with the service name,
path, status and time, and returned in the response header. The assistant sends the id on every call it makes, so one
scenario run can be followed through the five services in Cloud Logging with a single query on the id."""
import json
import logging
import time
import uuid

HEADER = "X-Correlation-Id"
_log = logging.getLogger("uvicorn.error")          # has a handler and INFO level on Cloud Run, unlike the app loggers
_QUIET = ("/health",)


def install(app, service: str) -> None:
    @app.middleware("http")
    async def correlate(request, call_next):
        correlation_id = (request.headers.get(HEADER) or "")[:100] or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        started = time.time()
        response = await call_next(request)
        response.headers[HEADER] = correlation_id
        if request.url.path not in _QUIET:
            _log.info(json.dumps({"event": "http_request", "service": service, "correlation_id": correlation_id,
                                  "method": request.method, "path": request.url.path, "status": response.status_code,
                                  "ms": round((time.time() - started) * 1000)}))
        return response
