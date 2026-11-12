"""State of this service: orders, stock, approvals.

In-memory, single instance (Cloud Run max_instance_count = 1, see infra/main.tf).
Every change is a compare-and-set on E2A's InMemoryTransactionalStore, the reference
adapter of BaseTransactionalStore; a Firestore adapter of the same contract is the
backlog item that lifts the single-instance limit.
"""
from decimal import Decimal
from typing import List, Optional

from e2a import BaseCheckpointStore
from e2a_inmemory_adapters import InMemoryTransactionalStore

from ..models.schemas import Approval, Order, OrderRequest


class OrderStore:
    def __init__(self) -> None:
        self._db = InMemoryTransactionalStore()

    def create(self, order: Order) -> bool:
        """Insert once: a second create of the same order id changes nothing."""
        return self._db.put_if_version(f"order:{order.order_id}", order.model_dump(mode="json"), None).committed

    def update(self, order: Order) -> None:
        row = self._db.get_versioned(f"order:{order.order_id}")
        result = self._db.put_if_version(f"order:{order.order_id}", order.model_dump(mode="json"), row[1])
        if not result.committed:
            raise RuntimeError(f"order {order.order_id} changed concurrently")

    def get(self, tenant_id: str, order_id: str) -> Optional[Order]:
        raw = self._db.get(f"order:{order_id}")
        order = Order.model_validate(raw) if raw else None
        return order if order and order.tenant_id == tenant_id else None


class InventoryStore:
    """Available stock per SKU. reserve() and release() are compare-and-set loops."""

    def __init__(self, initial: dict) -> None:
        self._db = InMemoryTransactionalStore()
        for sku, quantity in initial.items():
            self._db.put(f"stock:{sku}", {"available": quantity})

    def available(self, sku: str) -> int:
        row = self._db.get(f"stock:{sku}")
        return int(row["available"]) if row else 0

    def reserve(self, sku: str, quantity: int) -> bool:
        while True:
            value, version = self._db.get_versioned(f"stock:{sku}") or (None, None)
            if value is None or value["available"] < quantity:
                return False
            if self._db.put_if_version(f"stock:{sku}", {"available": value["available"] - quantity},
                                       version).committed:
                return True

    def release(self, sku: str, quantity: int) -> None:
        while True:
            value, version = self._db.get_versioned(f"stock:{sku}")
            if self._db.put_if_version(f"stock:{sku}", {"available": value["available"] + quantity},
                                       version).committed:
                return


class ApprovalStore(BaseCheckpointStore):
    """The perimeter where a paused order waits for a human decision: E2A's checkpoint
    store (BaseWorkflow saves the checkpoint, resume() decides it exactly once), with each
    checkpoint also listed as an Approval for the API."""

    def __init__(self) -> None:
        self._db = InMemoryTransactionalStore()
        self._ids: List[str] = []

    def save(self, checkpoint, config=None, **kwargs) -> None:
        state = checkpoint["state"]
        approval = Approval(approval_id=checkpoint["checkpoint_id"], tenant_id=checkpoint["tenant_id"],
                            requested_by=checkpoint["requested_by"],
                            order_request=OrderRequest(**state["order_request"]),
                            amount=Decimal(str(state["amount"])), idempotency_key=checkpoint["idempotency_key"],
                            state=state)
        record = {"approval": approval.model_dump(mode="json"), "checkpoint": checkpoint}
        if self._db.put_if_version(f"approval:{approval.approval_id}", record, None).committed:
            self._ids.append(approval.approval_id)

    def load(self, checkpoint_id, config=None, tenant_id=None, **kwargs):
        raw = self._db.get(f"approval:{checkpoint_id}")
        if raw is None or raw["checkpoint"]["tenant_id"] != tenant_id:
            return None
        return dict(raw["checkpoint"], status=raw["approval"]["status"])

    def decide(self, checkpoint_id, status, decided_by, config=None, **kwargs) -> bool:
        """PENDING -> APPROVED | REJECTED as one compare-and-set."""
        raw, version = self._db.get_versioned(f"approval:{checkpoint_id}") or (None, None)
        if raw is None or raw["approval"]["status"] != "PENDING":
            return False
        decided = {"approval": dict(raw["approval"], status=status, decided_by=decided_by),
                   "checkpoint": dict(raw["checkpoint"], status=status)}
        return self._db.put_if_version(f"approval:{checkpoint_id}", decided, version).committed

    def get(self, tenant_id: str, approval_id: str) -> Optional[Approval]:
        raw = self._db.get(f"approval:{approval_id}")
        approval = Approval.model_validate(raw["approval"]) if raw else None
        return approval if approval and approval.tenant_id == tenant_id else None

    def list(self, tenant_id: str, status: Optional[str] = None) -> List[Approval]:
        rows = [self.get(tenant_id, approval_id) for approval_id in list(self._ids)]
        return [a for a in rows if a is not None and (status is None or a.status == status)]
