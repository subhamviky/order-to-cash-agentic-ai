"""State of this service: orders, stock, approvals.

Every change is a compare-and-set on an E2A BaseTransactionalStore (services/state.py chooses
it): the in-memory reference adapter for tests and one instance, or e2a-adapters' Firestore
adapter, durable and shared, so that several Cloud Run instances serve the same orders, stock
and approvals (design note D-03).
"""
import time
from decimal import Decimal
from typing import Dict, List, Optional

from e2a import BaseCheckpointStore, BaseTransactionalStore
from e2a_inmemory_adapters import InMemoryTransactionalStore

from ..models.schemas import Approval, Order, OrderRequest
from .events import DEFAULT_TOPIC, order_event
from .paged_index import PagedIndex


FINAL_STATUSES = ("PAID", "CANCELLED", "REFUSED")


class OpenOrders:
    """The orders not yet final, so a scheduled sweep can find the ones a crash left behind (the
    transactional store has no queries). One document, {"<tenant>/<order_id>": since}, changed by
    compare-and-set; it holds only unfinished orders, so it stays small.

    An order is listed BEFORE it is first written and removed only AFTER it is final, so a crash
    between the two writes leaves it listed, never lost: the sweep removes an entry whose order
    is final or (after the grace period) does not exist."""

    KEY = "open-orders"

    def __init__(self, db: BaseTransactionalStore, clock=time.time) -> None:
        self._db, self.clock = db, clock

    def _change(self, update) -> None:
        while True:
            value, version = self._db.get_versioned(self.KEY) or ({"orders": {}}, None)
            orders = dict(value.get("orders", {}))
            if not update(orders):
                return
            if self._db.put_if_version(self.KEY, {"orders": orders}, version).committed:
                return

    def add(self, tenant_id: str, order_id: str) -> None:
        entry = f"{tenant_id}/{order_id}"
        self._change(lambda orders: entry not in orders and orders.update({entry: self.clock()}) is None)

    def remove(self, tenant_id: str, order_id: str) -> None:
        entry = f"{tenant_id}/{order_id}"
        self._change(lambda orders: orders.pop(entry, None) is not None)

    def entries(self) -> Dict[str, float]:
        return dict((self._db.get(self.KEY) or {}).get("orders", {}))


class OrderStore:
    """Orders. When the store has an outbox (services/state.py gives it one), every change of
    status is committed together with its event (services/events.py). Every order not yet final
    is listed in OpenOrders (for the scheduled recovery sweep)."""

    def __init__(self, db: Optional[BaseTransactionalStore] = None, topic: str = DEFAULT_TOPIC) -> None:
        self._db = db or InMemoryTransactionalStore()
        self.topic = topic
        self.emits_events = getattr(self._db, "outbox", None) is not None
        self.open = OpenOrders(self._db)

    def _events(self, order: Order, previous_status: Optional[str]) -> List[dict]:
        if not self.emits_events or order.status == previous_status:
            return []
        event = order_event(order, self.topic)
        return [event] if event else []

    def create(self, order: Order) -> bool:
        """Insert once: a second create of the same order id changes nothing (and announces nothing)."""
        if order.status not in FINAL_STATUSES:
            self.open.add(order.tenant_id, order.order_id)          # listed before it exists
        return self._db.put_if_version(f"order:{order.order_id}", order.model_dump(mode="json"), None,
                                       outbox=self._events(order, None)).committed

    def update(self, order: Order) -> None:
        row = self._db.get_versioned(f"order:{order.order_id}")
        result = self._db.put_if_version(f"order:{order.order_id}", order.model_dump(mode="json"), row[1],
                                         outbox=self._events(order, row[0].get("status")))
        if not result.committed:
            raise RuntimeError(f"order {order.order_id} changed concurrently")
        if order.status in FINAL_STATUSES:
            self.open.remove(order.tenant_id, order.order_id)       # removed once it is final

    def get(self, tenant_id: str, order_id: str) -> Optional[Order]:
        raw = self._db.get(f"order:{order_id}")
        order = Order.model_validate(raw) if raw else None
        return order if order and order.tenant_id == tenant_id else None


class InventoryStore:
    """Available stock per SKU. reserve() and release() are compare-and-set loops.

    A change may carry a key (the order's ``ORD-...:reserve`` / ``ORD-...:release``). The key is
    recorded in the stock document in the same compare-and-set as the change, so repeating a keyed
    change does nothing: a resumed order saga can never reserve or release twice. forget() drops
    the keys once the order is final, so the document stays small."""

    def __init__(self, initial: dict, db: Optional[BaseTransactionalStore] = None) -> None:
        self._db = db or InMemoryTransactionalStore()
        for sku, quantity in initial.items():
            # Create-if-absent: with a shared store every instance starts with this catalog, and
            # a restart must not reset stock that orders have already reserved.
            self._db.put_if_version(f"stock:{sku}", {"available": quantity}, None)

    def available(self, sku: str) -> int:
        row = self._db.get(f"stock:{sku}")
        return int(row["available"]) if row else 0

    def applied(self, sku: str) -> dict:
        """The keyed changes not yet forgotten: {key: change}."""
        row = self._db.get(f"stock:{sku}")
        return dict((row or {}).get("applied", {}))

    def reserve(self, sku: str, quantity: int, key: Optional[str] = None) -> bool:
        return self._change(sku, -quantity, key)

    def release(self, sku: str, quantity: int, key: Optional[str] = None) -> None:
        self._change(sku, quantity, key)

    def forget(self, sku: str, *keys: str) -> None:
        while True:
            value, version = self._db.get_versioned(f"stock:{sku}") or (None, None)
            applied = dict((value or {}).get("applied", {}))
            if value is None or not any(k in applied for k in keys):
                return
            for k in keys:
                applied.pop(k, None)
            if self._db.put_if_version(f"stock:{sku}", dict(value, applied=applied), version).committed:
                return

    def _change(self, sku: str, delta: int, key: Optional[str]) -> bool:
        while True:
            value, version = self._db.get_versioned(f"stock:{sku}") or (None, None)
            if value is None:
                return False
            applied = dict(value.get("applied", {}))
            if key is not None and key in applied:
                return True                                # this change was already made
            if value["available"] + delta < 0:
                return False
            if key is not None:
                applied[key] = delta
            row = {"available": value["available"] + delta, **({"applied": applied} if applied else {})}
            if self._db.put_if_version(f"stock:{sku}", row, version).committed:
                return True


class ApprovalStore(BaseCheckpointStore):
    """The perimeter where a paused order waits for a human decision: E2A's checkpoint
    store (BaseWorkflow saves the checkpoint, resume() decides it exactly once), with each
    checkpoint also listed as an Approval for the API."""

    def __init__(self, db: Optional[BaseTransactionalStore] = None) -> None:
        self._db = db or InMemoryTransactionalStore()

    def save(self, checkpoint, config=None, **kwargs) -> None:
        state = checkpoint["state"]
        approval = Approval(approval_id=checkpoint["checkpoint_id"], tenant_id=checkpoint["tenant_id"],
                            requested_by=checkpoint["requested_by"],
                            order_request=OrderRequest(**state["order_request"]),
                            amount=Decimal(str(state["amount"])), idempotency_key=checkpoint["idempotency_key"],
                            state=state)
        record = {"approval": approval.model_dump(mode="json"), "checkpoint": checkpoint}
        if self._db.put_if_version(f"approval:{approval.approval_id}", record, None).committed:
            self._index(approval.tenant_id, approval.approval_id)

    def _index(self, tenant_id: str, approval_id: str) -> None:
        """The tenant's approval ids, in a paged index (compare-and-set): every instance lists the
        same approvals, and no index document outgrows the store's limit."""
        PagedIndex(self._db, f"approvals:{tenant_id}").append(approval_id)

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
        ids = PagedIndex(self._db, f"approvals:{tenant_id}").ids()
        rows = [self.get(tenant_id, approval_id) for approval_id in ids]
        return [a for a in rows if a is not None and (status is None or a.status == status)]
