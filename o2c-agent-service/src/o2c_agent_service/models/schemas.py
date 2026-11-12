"""Request, response and domain records. Money is always Decimal, never float."""
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Intent = Literal["PLACE_ORDER", "ORDER_STATUS", "PAYMENT_EXCEPTIONS", "POLICY_QUESTION", "UNSUPPORTED"]
OrderStatus = Literal["PENDING_PAYMENT", "PAID", "CANCELLED", "PAYMENT_UNKNOWN", "REFUSED"]


class AssistantRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class OrderRequest(BaseModel):
    """What the intake agent extracted from the text; checked against the catalog."""
    customer_id: str
    sku: str
    quantity: int = Field(gt=0, le=1000)


class Order(BaseModel):
    order_id: str
    tenant_id: str
    customer_id: str
    sku: str
    quantity: int
    amount: Decimal
    currency: str
    status: OrderStatus
    requested_by: str
    idempotency_key: str
    approved_by: Optional[str] = None
    settlement_id: Optional[str] = None
    settlement_status: Optional[str] = None
    reason: Optional[str] = None


class Approval(BaseModel):
    approval_id: str
    tenant_id: str
    requested_by: str
    order_request: OrderRequest
    amount: Decimal
    idempotency_key: str
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    decided_by: Optional[str] = None
    state: Dict[str, Any] = Field(default_factory=dict)      # the dehydrated workflow state


class AssistantResponse(BaseModel):
    status: str                      # COMPLETED | AWAITING_APPROVAL | NEEDS_CLARIFICATION | REFUSED | REPLAYED | ...
    intent: Optional[str] = None
    answer: str
    order: Optional[Order] = None
    approval_id: Optional[str] = None
    citations: List[str] = Field(default_factory=list)
    degraded: bool = False
    correlation_id: Optional[str] = None
