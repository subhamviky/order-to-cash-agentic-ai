"""Governed tools on E2A BaseToolService.

execute() (inherited, public) validates the input, applies the commit gate, and runs the
call through the per-tool ResiliencePolicy (retry budget, circuit breaker, bulkhead).
A call is retried only when it is replay-safe (an idempotency key, or a read marked
safe_to_retry), and a timeout becomes the typed outcome UNKNOWN, never a blind retry.
Every result carries physical_success and outcome: the agent's text is never the truth.
The tenant travels in the payload: execute() keeps tenant_id as its own parameter and does
not hand it on to the transport hook.
"""
from typing import Any, Callable, Dict, Optional

import httpx
from e2a_base import BaseToolService, PhysicalOutcome, RestToolService


class HttpJsonTool(RestToolService):
    """One HTTP endpoint of another service of the landscape."""

    def __init__(self, name: str, base_url: str, method: str, path: str, required: tuple = (),
                 success: Callable[[int, Any], bool] = None, definitive: Callable[[int, Any], bool] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.name, self.base_url, self.method, self.path = name, base_url.rstrip("/"), method, path
        self.required = required
        self.success = success or (lambda status, body: 200 <= status < 300)
        self.definitive = definitive or (lambda status, body: 400 <= status < 500)
        self.transport = transport

    def get_endpoint(self, config=None, tenant_id=None, **kwargs):
        return self.base_url + self.path

    def _validate_input(self, payload, config=None, **kwargs):
        return all(payload.get(f) not in (None, "") for f in ("tenant_id",) + self.required)

    def _build_payload(self, payload, config=None, **kwargs):
        return payload

    async def _send_request(self, endpoint, body, token=None, timeout=None, config=None, **kwargs):
        body = dict(body)
        headers = {"X-Tenant-Id": body.pop("tenant_id")}
        if kwargs.get("idempotency_key"):
            headers["Idempotency-Key"] = kwargs["idempotency_key"]
        url = endpoint.format(**body)
        params = body.pop("params", None)
        json_body = body.pop("json", None)
        async with httpx.AsyncClient(transport=self.transport, timeout=timeout) as client:
            response = await client.request(self.method, url, params=params, json=json_body, headers=headers)
        data = response.json() if response.content else None
        if response.status_code >= 500:
            # not definitive: raise so the resilience policy may retry a replay-safe call
            raise RuntimeError(f"{self.name}: HTTP {response.status_code}")
        ok = self.success(response.status_code, data)
        outcome = (PhysicalOutcome.COMMITTED if ok else
                   PhysicalOutcome.NOT_COMMITTED if self.definitive(response.status_code, data) else
                   PhysicalOutcome.UNKNOWN)
        return {"status": response.status_code, "physical_success": ok, "outcome": outcome, "body": data}


class LocalTool(BaseToolService):
    """A tool implemented inside this service (stock, orders), behind the same contract."""

    def __init__(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]], required: tuple = ()) -> None:
        self.name, self.fn, self.required = name, fn, required

    def get_endpoint(self, config=None, tenant_id=None, **kwargs):
        return f"local://{self.name}"

    def _validate_input(self, payload, config=None, **kwargs):
        return all(payload.get(f) not in (None, "") for f in ("tenant_id",) + self.required)

    def _build_payload(self, payload, config=None, **kwargs):
        return payload

    async def _send_request(self, endpoint, body, token=None, timeout=None, config=None, **kwargs):
        return self.fn(dict(body))


def settlement_tools(base_url: str, transport=None) -> Dict[str, HttpJsonTool]:
    completed = lambda status, body: status == 201 and (body or {}).get("status") == "COMPLETED"
    return {
        # Material: money moves. Replay-safe because settlement-service de-duplicates on Idempotency-Key.
        "submit_settlement": HttpJsonTool(
            "submit_settlement", base_url, "POST", "/api/v1/settlements", required=("json",),
            success=completed, definitive=lambda status, body: status in (201, 400, 404, 409, 422),
            transport=transport),
        "get_settlement": HttpJsonTool(
            "get_settlement", base_url, "GET", "/api/v1/settlements/{settlement_id}",
            required=("settlement_id",), transport=transport),
    }


def reconciliation_tools(base_url: str, transport=None) -> Dict[str, HttpJsonTool]:
    return {"open_exceptions": HttpJsonTool("open_exceptions", base_url, "GET", "/api/v1/exceptions",
                                            transport=transport)}
