"""OrderExecutionAgent: places an order as a deterministic saga through governed tools.

E2A runs either the governance engine's gate or _apply_policy; this agent executes tools,
so its _apply_policy calls the composed engine's PUBLIC gate first (capacity, budget,
human approval, firewall) and only then the tools (E2A reference: tool calls live in
_apply_policy). Steps: price -> approval gate -> credit -> reserve stock -> settlement.
A failed settlement releases the stock (compensation); a timeout is UNKNOWN and the
order waits for recovery with the same idempotency key. The answer text never decides
the status: only the tools' typed outcomes do (Logical-vs-Physical rule).
"""
import hashlib
import logging

from e2a_base import BaseAgent, PhysicalOutcome

from ..models.schemas import Order, OrderRequest
from ..services.catalog import Catalog
from ..services.governance import O2CGovernance
from ..services.llm import EXECUTION
from ..services.stores import OrderStore
from ..tools.gateway import ToolGateway


def order_id_for(idempotency_key: str) -> str:
    return "ORD-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:10].upper()


class OrderExecutionAgent(BaseAgent):
    agent_name = 'OrderExecutionAgent'

    def __init__(self, catalog: Catalog, orders: OrderStore, tools: ToolGateway, governance: O2CGovernance) -> None:
        self.catalog, self.orders, self.tools, self.governance = catalog, orders, tools, governance

    def _build_messages(self, state, config=None, **kwargs) -> list:
        r = state['order_request']
        return [{'role': 'system', 'content': f'You are the {EXECUTION}. Acknowledge the order request.'},
                {'role': 'user', 'content': f"{r['quantity']} x {r['sku']} for {r['customer_id']}"}]

    def _apply_policy(self, state, config=None, **kwargs) -> None:
        request = OrderRequest(**state['order_request'])
        tenant = kwargs['tenant_id']
        amount = self.catalog.price(request.sku, request.quantity)
        state['amount'] = str(amount)
        state['requires_human_approval'] = amount > self.governance.policy.approval_threshold
        io_config = {**kwargs['io_config'], 'max_token_budget': self.governance.policy.max_token_budget}
        self.governance.enforce_governance_gate(state, io_config, config,
                                                correlation_id=kwargs['correlation_id'], tenant_id=tenant)

        key = state['idempotency_key']
        order = Order(order_id=order_id_for(key), tenant_id=tenant, customer_id=request.customer_id,
                      sku=request.sku, quantity=request.quantity, amount=amount, currency=self.catalog.currency,
                      status='PENDING_PAYMENT', requested_by=state['user_id'], idempotency_key=key,
                      approved_by=state.get('approved_by'))
        customer = self.catalog.customers[request.customer_id]
        if amount > customer.credit_limit:
            return self._finish(state, order, 'REFUSED', PhysicalOutcome.NOT_COMMITTED,
                                f'amount {amount} exceeds the credit limit {customer.credit_limit} (POL-CREDIT-01)')
        reserved = self.tools.call(self.agent_name, 'reserve_stock',
                                   {'sku': request.sku, 'quantity': request.quantity}, tenant)
        if not reserved['physical_success']:
            return self._finish(state, order, 'REFUSED', PhysicalOutcome.NOT_COMMITTED, 'insufficient stock')
        self.orders.create(order)

        settlement = self.tools.call(self.agent_name, 'submit_settlement', {'json': {
            'payerAccount': customer.payer_account, 'payeeAccount': self.catalog.receivable_account,
            'amount': str(amount), 'currency': self.catalog.currency}}, tenant, idempotency_key=order.order_id)
        apply_settlement_result(order, settlement, self.tools, self.agent_name, tenant)
        self.orders.update(order)
        state['order'] = order.model_dump(mode='json')
        state['outcome'] = settlement['outcome'].value

    def _finish(self, state, order, status, outcome, reason) -> None:
        order.status, order.reason = status, reason
        self.orders.create(order)
        state['order'] = order.model_dump(mode='json')
        state['outcome'] = outcome.value

    def _evaluate_output(self, response, state, config=None, **kwargs) -> float:
        response['order'] = state.get('order')
        return 1.0 if state.get('outcome') in ('COMMITTED', 'NOT_COMMITTED') else 0.0

    def _fallback(self, state, config=None, **kwargs):
        return {'text': 'payment outcome unknown', 'order': state.get('order'), 'degraded': True}

    def _handle_error(self, error, state, config=None, **kwargs):
        logging.error(f'[{self.agent_name}] {error}')
        state.setdefault('errors', []).append(str(error))
        return state


def apply_settlement_result(order: Order, settlement: dict, tools: ToolGateway, agent: str, tenant: str) -> None:
    """Map the settlement tool's typed outcome onto the order (also used by recovery)."""
    body = settlement.get('body') or {}
    outcome = settlement['outcome']
    if outcome == PhysicalOutcome.COMMITTED:
        order.status, order.settlement_id, order.settlement_status = 'PAID', body.get('settlementId'), body.get('status')
        order.reason = None
    elif outcome == PhysicalOutcome.NOT_COMMITTED:
        tools.call(agent, 'release_stock', {'sku': order.sku, 'quantity': order.quantity}, tenant)
        order.status, order.settlement_id = 'CANCELLED', body.get('settlementId')
        order.settlement_status = body.get('status')
        order.reason = body.get('reason') or body.get('error') or f"settlement HTTP {settlement.get('status')}"
    else:
        order.status, order.reason = 'PAYMENT_UNKNOWN', settlement.get('error') or 'no answer from settlement-service'
