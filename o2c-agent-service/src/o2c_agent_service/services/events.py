"""Order events: what other services learn about an order, published exactly once per change.

An order's row and its event are written in ONE commit (E2A v1.7.3:
put_if_version(..., outbox=[record])): the event is pending if and only if the change was
committed, so no change goes unannounced and no event announces a change that was not made.
A sweeper (E2A BrokerOutboxSweeper, under a lease) publishes pending events to the events
topic; Cloud Scheduler calls POST /internal/events/publish for it. Each event carries the
tenant and an idempotency key (order id and status), so a consumer's claim makes a second
publication harmless.
"""
from typing import Any, Dict, Optional

from ..models.schemas import Order

# the event announcing that an order reached a status
EVENT_TYPES = {
    "PENDING_PAYMENT": "order.placed",
    "PAID": "order.paid",
    "PAYMENT_UNKNOWN": "order.payment_unknown",
    "CANCELLED": "order.cancelled",
    "REFUSED": "order.refused",
}

DEFAULT_TOPIC = "o2c-order-events"


def order_event(order: Order, topic: str) -> Optional[Dict[str, Any]]:
    """The outbox record announcing the order's current status, or None for a status that
    has no event."""
    event_type = EVENT_TYPES.get(order.status)
    if event_type is None:
        return None
    body = {"event_type": event_type, **order.model_dump(mode="json",
                                                         include={"order_id", "tenant_id", "customer_id", "sku",
                                                                  "quantity", "amount", "currency", "status",
                                                                  "settlement_id", "reason"})}
    return {"destination": topic, "body": body,
            "attributes": {"event_type": event_type, "order_id": order.order_id},
            "tenant_id": order.tenant_id, "idempotency_key": f"{order.order_id}:{order.status}"}
