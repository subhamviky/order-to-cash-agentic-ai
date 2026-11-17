"""OrderExecutionAgent: places an order as a deterministic saga (E2A v1.2 contract).

_prepare prices the order (a read); the governance stages then decide whether a human
must approve it (the workflow pauses and resume() continues here). There is no model
step: _act runs the saga through io_modify, every material call with its own
idempotency key. The typed outcomes, never a text, decide the result (E2A _confirm:
UNKNOWN > NOT_COMMITTED > COMMITTED).

The saga is resumable (advance_order): the order is recorded as RESERVING before any stock
moves, and every step continues from the order's status with the same keys:

  credit limit        refused -> REFUSED (nothing recorded before)
  RESERVING           reserve_stock (ORD-...:reserve)  -> PENDING_PAYMENT | REFUSED
  PENDING_PAYMENT     submit_settlement (key ORD-...)  -> PAID | CANCELLED (release_stock
  PAYMENT_UNKNOWN                                         ORD-...:release) | PAYMENT_UNKNOWN

A crash at any point leaves an order that O2CRecovery finishes with the same calls: the stock
keys make a repeated reservation or release a no-op, and settlement-service de-duplicates
the payment on the order id. No order is charged twice, and no stock is lost or counted twice.
"""
import hashlib
from decimal import Decimal

from e2a import BaseAgent, PhysicalOutcome

from ..models.schemas import Order, OrderRequest
from ..services.catalog import Catalog
from ..services.stores import InventoryStore, OrderStore

FINAL = ("PAID", "CANCELLED", "REFUSED")


def order_id_for(idempotency_key: str) -> str:
    return "ORD-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10].upper()


class OrderExecutionAgent(BaseAgent):
    agent_name = 'OrderExecutionAgent'

    def __init__(self, catalog: Catalog, orders: OrderStore, inventory: InventoryStore) -> None:
        self.catalog, self.orders, self.inventory = catalog, orders, inventory

    def _prepare(self, state, ctx) -> None:
        request = OrderRequest(**state['order_request'])
        state['amount'] = str(self.catalog.price(request.sku, request.quantity))

    def _build_messages(self, state, ctx):
        return None                                   # a deterministic saga: no model step

    def _act(self, state, ctx, io_modify) -> list:
        request, amount = OrderRequest(**state['order_request']), Decimal(state['amount'])
        order_id = order_id_for(ctx.idempotency_key)
        order = self.orders.get(ctx.tenant_id, order_id)
        if order is None:
            order = Order(order_id=order_id, tenant_id=ctx.tenant_id,
                          customer_id=request.customer_id, sku=request.sku, quantity=request.quantity, amount=amount,
                          currency=self.catalog.currency, status='RESERVING', requested_by=state['user_id'],
                          idempotency_key=ctx.idempotency_key, approved_by=state.get('approved_by'))
            customer = self.catalog.customers[request.customer_id]
            if amount > customer.credit_limit:
                order.status, order.reason = 'REFUSED', (f'amount {amount} exceeds the credit limit '
                                                         f'{customer.credit_limit} (POL-CREDIT-01)')
                self.orders.create(order)
                respond(state, order)
                return [PhysicalOutcome.NOT_COMMITTED]
            self.orders.create(order)                 # RESERVING: no event; nothing has moved yet
        outcomes = advance_order(order, self.catalog, self.orders, self.inventory, io_modify)
        respond(state, order)
        return outcomes or [outcome_of(order)]


def advance_order(order: Order, catalog: Catalog, orders: OrderStore, inventory: InventoryStore, io_modify) -> list:
    """Continue the saga from the order's status (used by the agent and by recovery).
    Returns the outcomes of the calls it made; the order is updated in the store."""
    outcomes = []
    if order.status == 'RESERVING':
        reserved = io_modify.call('reserve_stock', {'sku': order.sku, 'quantity': order.quantity},
                                  idempotency_key=f'{order.order_id}:reserve')
        outcomes.append(reserved)
        if reserved['physical_success']:
            order.status = 'PENDING_PAYMENT'
        else:
            order.status, order.reason = 'REFUSED', 'insufficient stock'
        orders.update(order)
    if order.status in ('PENDING_PAYMENT', 'PAYMENT_UNKNOWN'):
        customer = catalog.customers[order.customer_id]
        settlement = io_modify.call('submit_settlement', {'json': {
            'payerAccount': customer.payer_account, 'payeeAccount': catalog.receivable_account,
            'amount': str(order.amount), 'currency': order.currency}}, idempotency_key=order.order_id)
        outcomes += [settlement, *apply_settlement_result(order, settlement, io_modify)]
        orders.update(order)
    if order.status in FINAL:                         # the stock keys are no longer needed
        inventory.forget(order.sku, f'{order.order_id}:reserve', f'{order.order_id}:release')
    return outcomes


def outcome_of(order: Order) -> PhysicalOutcome:
    """The physical truth an order's status stands for."""
    if order.status == 'PAID':
        return PhysicalOutcome.COMMITTED
    if order.status in ('CANCELLED', 'REFUSED'):
        return PhysicalOutcome.NOT_COMMITTED
    return PhysicalOutcome.UNKNOWN


def respond(state, order: Order) -> None:
    """The deterministic agent's response: the order, degraded while the payment is unknown."""
    state['order'] = order.model_dump(mode='json')
    state['response'] = {'order': state['order'], 'degraded': order.status == 'PAYMENT_UNKNOWN'}


def apply_settlement_result(order: Order, settlement: dict, io_modify) -> list:
    """Map the settlement tool's typed outcome onto the order (also used by recovery).
    Returns the outcomes of any compensation it ran."""
    body = settlement.get('body') or {}
    outcome = settlement['outcome']
    if outcome == PhysicalOutcome.COMMITTED:
        order.status, order.settlement_id, order.settlement_status = 'PAID', body.get('settlementId'), body.get('status')
        order.reason = None
        return []
    if outcome == PhysicalOutcome.NOT_COMMITTED:
        released = io_modify.call('release_stock', {'sku': order.sku, 'quantity': order.quantity},
                                  idempotency_key=f'{order.order_id}:release')
        order.status, order.settlement_id = 'CANCELLED', body.get('settlementId')
        order.settlement_status = body.get('status')
        order.reason = body.get('reason') or body.get('error') or f"settlement HTTP {settlement.get('status')}"
        return [released]
    order.status, order.reason = 'PAYMENT_UNKNOWN', settlement.get('error') or 'no answer from settlement-service'
    return []
