"""FinanceAgent: answers payment questions from the systems of record (E2A v1.2 contract).

The facts are read in _prepare through io_read (replay-safe reads, limited by the
governance tool_policy). The model only phrases them; _evaluate_output rejects any answer
that mentions an identifier, amount or status the facts do not contain, and the fallback
is the plain list of facts.
"""
import logging
import re

from e2a import BaseAgent

from ..services.llm import FINANCE

ORDER_ID = re.compile(r"\bORD-[A-Z0-9]{10}\b")
CHECKED = re.compile(r"\bORD-[A-Z0-9]+\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
                     r"|\b\d+\.\d{2}\b|\b[A-Z][A-Z_]{3,}\b")


class FinanceAgent(BaseAgent):
    agent_name = 'FinanceAgent'

    def _apply_policy(self, state, ctx) -> None:
        if state.get('intent') not in ('ORDER_STATUS', 'PAYMENT_EXCEPTIONS'):
            raise ValueError(f"FinanceAgent cannot handle {state.get('intent')}")

    def _prepare(self, state, ctx, io_read) -> None:
        state['facts'] = (self._order_facts(state, io_read) if state.get('intent') == 'ORDER_STATUS'
                          else self._exception_facts(io_read))

    def _order_facts(self, state, io_read) -> list:
        match = ORDER_ID.search(state['query'])
        if not match:
            return ['No order id (ORD-...) was given.']
        order = io_read.call('get_order', {'order_id': match.group(0)}).get('order')
        if not order:
            return [f'Order {match.group(0)} does not exist for this tenant.']
        facts = [f"Order {order['order_id']} is {order['status']}: {order['quantity']} x {order['sku']} "
                 f"for {order['customer_id']}, amount {order['amount']} {order['currency']}"]
        if order.get('settlement_id'):
            s = io_read.call('get_settlement', {'settlement_id': order['settlement_id']})
            facts.append(f"Settlement {order['settlement_id']} is {s['body']['status']} in settlement-service"
                         if s['physical_success'] else 'settlement-service did not answer; status not confirmed')
        return facts

    def _exception_facts(self, io_read) -> list:
        result = io_read.call('open_exceptions', {'params': {'status': 'OPEN'}})
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

    def _build_messages(self, state, ctx) -> list:
        facts = state['facts']
        return [{'role': 'system', 'content': f'You are the {FINANCE}. Answer only from the facts listed.'},
                {'role': 'user', 'content': state['query'] + '\nFacts:\n' + '\n'.join(f'- {f}' for f in facts)}]

    def _evaluate_output(self, response, state, ctx) -> float:
        text = (response or {}).get('text', '')
        evidence = ' '.join(state.get('facts', []))
        unsupported = [t for t in CHECKED.findall(text) if t not in evidence]
        state['unsupported_claims'] = unsupported
        return 0.0 if (not text or unsupported) else 1.0

    def _fallback(self, state, ctx):
        return {'text': ' '.join(f if f.endswith('.') else f + '.' for f in state.get('facts', [])),
                'degraded': True}

    def _handle_error(self, error, state, ctx):
        logging.error(f'[{self.agent_name}] {error}')
        state.setdefault('errors', []).append(str(error))
