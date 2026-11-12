"""Recovery of orders whose payment outcome is UNKNOWN, on E2A BaseReconciliationService.

reconcile() (inherited, public) takes over each parked idempotency claim (recover=True),
asks _confirm_physical_outcome() for the physical truth and only then settles the claim:
COMMITTED completes it, so a repeat of the order is REPLAYED; UNKNOWN stays parked. The
truth comes from settlement-service: the payment is re-sent with the SAME idempotency
key, which settlement-service de-duplicates and answers with the original result, so a
customer is never charged twice.
"""
from typing import Any, Dict, List

from e2a import BaseReconciliationService, ModifyAccess, PhysicalOutcome, RequestContext

from ..agents.order_execution_agent import apply_settlement_result
from .catalog import Catalog
from .governance import GovernancePolicy
from .stores import OrderStore


class O2CRecovery(BaseReconciliationService):
    def __init__(self, orders: OrderStore, catalog: Catalog, policy: GovernancePolicy, idempotency_store) -> None:
        super().__init__(idempotency_store=idempotency_store)
        self.orders, self.catalog, self.policy = orders, catalog, policy

    def _fetch_dlq_entries(self, config=None, tenant_id=None, order_id=None, **kwargs) -> List[Dict[str, Any]]:
        order = self.orders.get(tenant_id, order_id)
        if order is None or order.status != "PAYMENT_UNKNOWN":
            return []
        return [{"id": order.order_id, "idempotency_key": order.idempotency_key, "tenant_id": tenant_id}]

    def _confirm_physical_outcome(self, entry, config=None, **kwargs) -> PhysicalOutcome:
        order = self.orders.get(entry["tenant_id"], entry["id"])
        customer = self.catalog.customers[order.customer_id]
        ctx = RequestContext.begin(tenant_id=entry["tenant_id"], config=config, idempotency_key=order.order_id)
        io_modify = ModifyAccess(ctx, config, allowed=self.policy.tools["OrderExecutionAgent"])
        settlement = io_modify.call("submit_settlement", {"json": {
            "payerAccount": customer.payer_account, "payeeAccount": self.catalog.receivable_account,
            "amount": str(order.amount), "currency": order.currency}})
        apply_settlement_result(order, settlement, io_modify)
        self.orders.update(order)
        # what a repeat of the order replays once the claim is completed
        entry["result"] = {"response": {"order": order.model_dump(mode="json"), "degraded": False},
                           "outcome": settlement["outcome"].value}
        return settlement["outcome"]

    def _replay_dlq_entry(self, entry, config=None, **kwargs) -> bool:
        """Reached for NOT_COMMITTED: settlement-service declined the payment, and
        apply_settlement_result() has already cancelled the order and released the stock.
        The order is final; nothing is re-sent."""
        return True
