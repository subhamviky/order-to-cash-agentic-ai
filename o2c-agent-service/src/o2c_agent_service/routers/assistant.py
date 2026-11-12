"""HTTP surface. Caller identity comes from headers (X-Tenant-Id, X-User-Id, X-User-Role);
authentication in front of it (Cloud Run IAM / an identity-aware proxy) is backlog."""
from typing import List, Optional

from e2a_base import NFRViolationError
from fastapi import APIRouter, Header, HTTPException, Request

from ..models.schemas import Approval, AssistantRequest, AssistantResponse, Order
from ..services.assistant import Forbidden, NotFound

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
def ask(body: AssistantRequest, request: Request, x_tenant_id: str = Header(""), x_user_id: str = Header(""),
        x_user_role: str = Header(""), idempotency_key: Optional[str] = Header(None)) -> AssistantResponse:
    return _call(_assistant(request).handle, body.text, x_tenant_id, x_user_id, x_user_role, idempotency_key)


@router.get("/api/v1/approvals", response_model=List[Approval])
def approvals(request: Request, x_tenant_id: str = Header(""), status: Optional[str] = None) -> List[Approval]:
    return _assistant(request).approvals.list(x_tenant_id, status)


@router.post("/api/v1/approvals/{approval_id}/approve", response_model=AssistantResponse)
def approve(approval_id: str, request: Request, x_tenant_id: str = Header(""), x_user_id: str = Header(""),
            x_user_role: str = Header("")) -> AssistantResponse:
    return _call(_assistant(request).approve, approval_id, x_tenant_id, x_user_id, x_user_role)


@router.post("/api/v1/approvals/{approval_id}/reject", response_model=AssistantResponse)
def reject(approval_id: str, request: Request, x_tenant_id: str = Header(""), x_user_id: str = Header(""),
           x_user_role: str = Header("")) -> AssistantResponse:
    return _call(_assistant(request).reject, approval_id, x_tenant_id, x_user_id, x_user_role)


@router.get("/api/v1/orders/{order_id}", response_model=Order)
def get_order(order_id: str, request: Request, x_tenant_id: str = Header("")) -> Order:
    order = _assistant(request).orders.get(x_tenant_id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="unknown order")
    return order


@router.post("/api/v1/orders/{order_id}/recover", response_model=Order)
def recover(order_id: str, request: Request, x_tenant_id: str = Header("")) -> Order:
    return _call(_assistant(request).recover, order_id, x_tenant_id)


@router.get("/api/v1/usage")
def usage(request: Request) -> dict:
    """FinOps evidence: simulated model calls, tokens and cost since start-up."""
    return _assistant(request).llm.usage_summary()


@router.post("/mcp")
async def mcp(payload: dict, request: Request, x_tenant_id: str = Header("")) -> dict:
    """MCP (JSON-RPC 2.0): tools/list and tools/call for the read-only O2C tools."""
    return await _assistant(request).mcp.serve_async(payload, _assistant(request).config, tenant_id=x_tenant_id)
