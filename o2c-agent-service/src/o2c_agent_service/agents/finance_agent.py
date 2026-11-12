"""FinanceAgent: answers payment questions from the systems of record.

The facts are read through governed tools while the prompt is built (as E2A's reference
RAG agent retrieves in _build_messages). The model only phrases them; _evaluate_output
rejects any answer that mentions an identifier, amount or status the facts do not contain,
and the fallback is the plain list of facts.
"""
import logging
import re

from e2a_base import BaseAgent

from ..services.llm import FINANCE
from ..tools.gateway import ToolGateway

ORDER_ID = re.compile(r"\bORD-[A-Z0-9]{10}\b")
CHECKED = re.compile(r"\bORD-[A-Z0-9]+\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
                     r"|\b\d+\.\d{2}\b|\b[A-Z][A-Z_]{3,}\b")


class FinanceAgent(BaseAgent):
    agent_name = 'FinanceAgent'

    def __init__(self, tools: ToolGateway) -> None:
        self.tools = tools

    def _build_messages(self, state, config=None, **kwargs) -> list:
        tenant = kwargs['tenant_id']
        facts = (self._order_facts(state, tenant) if state['intent'] == 'ORDER_STATUS'
                 else self._exception_facts(tenant))
        state['facts'] = facts
        return [{'role': 'system', 'content': f'You are the {FINANCE}. Answer only from the facts listed.'},
                {'role': 'user', 'content': state['query'] + '\nFacts:\n' + '\n'.join(f'- {f}' for f in facts)}]

    def _order_facts(self, state, tenant) -> list:
        match = ORDER_ID.search(state['query'])
        if not match:
            return ['No order id (ORD-...) was given.']
        found = self.tools.call(self.agent_name, 'get_order', {'order_id': match.group(0)}, tenant)
        order = found.get('order')
        if not order:
            return [f'Order {match.group(0)} does not exist for this tenant.']
        facts = [f"Order {order['order_id']} is {order['status']}: {order['quantity']} x {order['sku']} "
                 f"for {order['customer_id']}, amount {order['amount']} {order['currency']}"]
        if order.get('settlement_id'):
            s = self.tools.call(self.agent_name, 'get_settlement', {'settlement_id': order['settlement_id']}, tenant)
            facts.append(f"Settlement {order['settlement_id']} is {s['body']['status']} in settlement-service"
                         if s['physical_success'] else 'settlement-service did not answer; status not confirmed')
        return facts

    def _exception_facts(self, tenant) -> list:
        result = self.tools.call(self.agent_name, 'open_exceptions', {'params': {'status': 'OPEN'}}, tenant)
        if not result['physical_success']:
            return ['reconciliation-service did not answer; open exceptions are unknown']
        cases = result['body'] or []
        if not cases:
            return ['There are no open reconciliation exceptions.']
        facts = [f'There are {len(cases)} open reconciliation exceptions']
        for c in cases:
            facts.append(f"Bank line {c['line_id']} is {c['kind']}: {c['detail']}; proposed action "
                         f"{c['proposal']['action']}")
        return facts

    def _apply_policy(self, state, config=None, **kwargs) -> None:
        if state.get('intent') not in ('ORDER_STATUS', 'PAYMENT_EXCEPTIONS'):
            raise ValueError(f"FinanceAgent cannot handle {state.get('intent')}")

    def _evaluate_output(self, response, state, config=None, **kwargs) -> float:
        text = (response or {}).get('text', '')
        evidence = ' '.join(state.get('facts', []))
        unsupported = [t for t in CHECKED.findall(text) if t not in evidence]
        state['unsupported_claims'] = unsupported
        return 0.0 if (not text or unsupported) else 1.0

    def _fallback(self, state, config=None, **kwargs):
        return {'text': ' '.join(f if f.endswith('.') else f + '.' for f in state.get('facts', [])),
                'degraded': True}

    def _handle_error(self, error, state, config=None, **kwargs):
        logging.error(f'[{self.agent_name}] {error}')
        state.setdefault('errors', []).append(str(error))
        return state
