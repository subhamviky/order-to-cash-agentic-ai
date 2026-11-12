"""OrderExecutionAgent: places an order as a deterministic saga (E2A v1.2 contract).

_prepare prices the order (a read); the governance stages then decide whether a human
must approve it (the workflow pauses and resume() continues here). There is no model
step: _act runs the saga through io_modify, every material call with its own
idempotency key: credit check -> reserve stock -> settlement. A failed settlement
releases the stock (compensation); a lost answer is UNKNOWN and the claim is parked for
recovery. The typed outcomes, never a text, decide the result (E2A _confirm: UNKNOWN >
NOT_COMMITTED > COMMITTED).
"""
import hashlib
from decimal import Decimal

from e2a import BaseAgent, PhysicalOutcome

from ..models.schemas import Order, OrderRequest
from ..services.catalog import Catalog
from ..services.stores import OrderStore


def order_id_for(idempotency_key: str) -> str:
    return "ORD-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10].upper()


class OrderExecutionAgent(BaseAgent):
    agent_name = 'OrderExecutionAgent'

    def __init__(self, catalog: Catalog, orders: OrderStore) -> None:
        self.catalog, self.orders = catalog, orders

    def _prepare(self, state, ctx) -> None:
        request = OrderRequest(**state['order_request'])
        state['amount'] = str(self.catalog.price(request.sku, request.quantity))

    def _build_messages(self, state, ctx):
        return None                                   # a deterministic saga: no model step

    def _act(self, state, ctx, io_modify) -> list:
        request, amount = OrderRequest(**state['order_request']), Decimal(state['amount'])
        order = Order(order_id=order_id_for(ctx.idempotency_key), tenant_id=ctx.tenant_id,
                      customer_id=request.customer_id, sku=request.sku, quantity=request.quantity, amount=amount,
                      currency=self.catalog.currency, status='PENDING_PAYMENT', requested_by=state['user_id'],
                      idempotency_key=ctx.idempotency_key, approved_by=state.get('approved_by'))
        customer = self.catalog.customers[request.customer_id]
        if amount > customer.credit_limit:
            return self._finish(state, order, 'REFUSED', f'amount {amount} exceeds the credit limit '
                                                         f'{customer.credit_limit} (POL-CREDIT-01)')
        reserved = io_modify.call('reserve_stock', {'sku': request.sku, 'quantity': request.quantity},
                                  idempotency_key=f'{order.order_id}:reserve')
        if not reserved['physical_success']:
            return self._finish(state, order, 'REFUSED', 'insufficient stock')
        self.orders.create(order)
        settlement = io_modify.call('submit_settlement', {'json': {
            'payerAccount': customer.payer_account, 'payeeAccount': self.catalog.receivable_account,
            'amount': str(amount), 'currency': self.catalog.currency}}, idempotency_key=order.order_id)
        compensation = apply_settlement_result(order, settlement, io_modify)
        self.orders.update(order)
        respond(state, order)
        return [reserved, settlement, *compensation]

    def _finish(self, state, order, status, reason) -> list:
        order.status, order.reason = status, reason
        self.orders.create(order)
        respond(state, order)
        return [PhysicalOutcome.NOT_COMMITTED]


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
