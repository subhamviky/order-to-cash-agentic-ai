"""Recovery of unfinished orders, on E2A BaseReconciliationService.

An order is unfinished when its payment outcome is UNKNOWN, or when a crash stopped its saga
part-way (RESERVING or PENDING_PAYMENT). reconcile() (inherited, public) takes over the order's
parked or expired idempotency claim (recover=True) - never one a live request still holds - asks
_confirm_physical_outcome() for the physical truth and only then settles the claim: COMMITTED
completes it, so a repeat of the order is REPLAYED; UNKNOWN stays parked.

The truth comes from continuing the saga (advance_order) with the SAME keys: a reservation or
release already made is not repeated, and the payment is re-sent with the same idempotency key,
which settlement-service de-duplicates and answers with the original result, so a customer is
never charged twice.
"""
from typing import Any, Dict, List

from e2a import BaseReconciliationService, ModifyAccess, PhysicalOutcome, RequestContext

from ..agents.order_execution_agent import advance_order, outcome_of
from .catalog import Catalog
from .governance import GovernancePolicy
from .stores import InventoryStore, OrderStore

UNFINISHED = ("RESERVING", "PENDING_PAYMENT", "PAYMENT_UNKNOWN")


class O2CRecovery(BaseReconciliationService):
    def __init__(self, orders: OrderStore, inventory: InventoryStore, catalog: Catalog, policy: GovernancePolicy,
                 idempotency_store) -> None:
        super().__init__(idempotency_store=idempotency_store)
        self.orders, self.inventory, self.catalog, self.policy = orders, inventory, catalog, policy

    def _fetch_dlq_entries(self, config=None, tenant_id=None, order_id=None, **kwargs) -> List[Dict[str, Any]]:
        order = self.orders.get(tenant_id, order_id)
        if order is None or order.status not in UNFINISHED:
            return []
        return [{"id": order.order_id, "idempotency_key": order.idempotency_key, "tenant_id": tenant_id}]

    def _confirm_physical_outcome(self, entry, config=None, **kwargs) -> PhysicalOutcome:
        order = self.orders.get(entry["tenant_id"], entry["id"])
        ctx = RequestContext.begin(tenant_id=entry["tenant_id"], config=config, idempotency_key=order.order_id)
        io_modify = ModifyAccess(ctx, config, allowed=self.policy.tools["OrderExecutionAgent"])
        advance_order(order, self.catalog, self.orders, self.inventory, io_modify)
        # what a repeat of the order replays once the claim is completed
        entry["result"] = {"response": {"order": order.model_dump(mode="json"), "degraded": False},
                           "outcome": outcome_of(order).value}
        return outcome_of(order)

    def _replay_dlq_entry(self, entry, config=None, **kwargs) -> bool:
        """Reached for NOT_COMMITTED: the order ended CANCELLED (payment declined, stock
        released) or REFUSED (no stock). The order is final; nothing is re-sent."""
        return True
