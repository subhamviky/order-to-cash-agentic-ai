"""HTTP surface. The caller (tenant, user, role) comes from routers/identity.py: in Google Cloud
from the claims API Gateway verified (E2A identity at ingress); locally from the X-Tenant-Id,
X-User-Id and X-User-Role headers."""
from typing import List, Optional

from e2a_base import NFRViolationError
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..models.schemas import Approval, AssistantRequest, AssistantResponse, Order
from ..services.assistant import Forbidden, NotFound
from .identity import Caller, caller

router = APIRouter()


def _assistant(request: Request):
    return request.app.state.assistant


def _call(fn, *args):
    try:
        return fn(*args)
    except Forbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NFRViolationError as e:                       # admission control: shed load, retry later
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/assistant", response_model=AssistantResponse)
def ask(body: AssistantRequest, request: Request, who: Caller = Depends(caller),
        idempotency_key: Optional[str] = Header(None)) -> AssistantResponse:
    return _call(_assistant(request).handle, body.text, who.tenant_id, who.user_id, who.role, idempotency_key)


@router.get("/api/v1/approvals", response_model=List[Approval])
def approvals(request: Request, who: Caller = Depends(caller), status: Optional[str] = None) -> List[Approval]:
    return _assistant(request).approvals.list(who.tenant_id, status)


@router.post("/api/v1/approvals/{approval_id}/approve", response_model=AssistantResponse)
def approve(approval_id: str, request: Request, who: Caller = Depends(caller)) -> AssistantResponse:
    return _call(_assistant(request).approve, approval_id, who.tenant_id, who.user_id, who.role)


@router.post("/api/v1/approvals/{approval_id}/reject", response_model=AssistantResponse)
def reject(approval_id: str, request: Request, who: Caller = Depends(caller)) -> AssistantResponse:
    return _call(_assistant(request).reject, approval_id, who.tenant_id, who.user_id, who.role)


@router.get("/api/v1/orders/{order_id}", response_model=Order)
def get_order(order_id: str, request: Request, who: Caller = Depends(caller)) -> Order:
    order = _assistant(request).orders.get(who.tenant_id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="unknown order")
    return order


@router.post("/api/v1/orders/{order_id}/recover", response_model=Order)
def recover(order_id: str, request: Request, who: Caller = Depends(caller)) -> Order:
    return _call(_assistant(request).recover, order_id, who.tenant_id)


@router.get("/api/v1/usage")
def usage(request: Request) -> dict:
    """FinOps evidence: simulated model calls, tokens and cost since start-up (the simulated
    model counts them; a provider model reports its usage to its own console)."""
    summary = getattr(_assistant(request).llm, "usage_summary", None)
    return summary() if callable(summary) else {"model": "provider", "usage": "reported by the provider"}


@router.post("/mcp")
async def mcp(payload: dict, request: Request, who: Caller = Depends(caller)) -> dict:
    """MCP (JSON-RPC 2.0): tools/list and tools/call for the read-only O2C tools."""
    return await _assistant(request).mcp.serve_async(payload, _assistant(request).config, tenant_id=who.tenant_id)


@router.post("/internal/orders/recover")
def recover_stuck_orders(request: Request) -> dict:
    """Finish the orders left unfinished by a crash or a lost answer. Cloud Scheduler calls this
    (infra/events.tf); only the service's invokers (Cloud Run IAM) can reach it, and API Gateway
    does not route it."""
    return _assistant(request).recover_stuck()


@router.post("/internal/events/publish")
def publish_events(request: Request) -> dict:
    """Publish pending order events to the events topic. Cloud Scheduler calls this on a
    schedule; only the service's invokers (Cloud Run IAM) can reach it."""
    return _assistant(request).publish_events()


@router.post("/internal/jobs/scheduled")
def scheduled_jobs(request: Request) -> dict:
    """Both scheduled jobs in one call (GCP-01): Cloud Scheduler's free tier is three jobs for the
    whole landscape, so O2C uses one. Pending order events are published first, then unfinished
    orders are recovered; a failure of one does not stop the other."""
    assistant, result = _assistant(request), {}
    for name, job in (("events", assistant.publish_events), ("recovery", assistant.recover_stuck)):
        try:
            result[name] = job()
        except Exception as e:                                # the next run tries again
            result[name] = {"error": type(e).__name__, "detail": str(e)[:200]}
    if all("error" in r for r in result.values() if isinstance(r, dict)):
        raise HTTPException(status_code=500, detail=result)
    return result
