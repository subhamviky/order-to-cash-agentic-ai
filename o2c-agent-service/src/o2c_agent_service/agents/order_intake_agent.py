"""OrderIntakeAgent: extracts {customer_id, sku, quantity} from the text (E2A v1.2 contract).
A PROPOSAL only: it is accepted when it parses, validates and names a known customer and
product. It reads and commits nothing."""
import json
import logging

from e2a import BaseAgent
from pydantic import ValidationError

from ..models.schemas import OrderRequest
from ..services.catalog import Catalog
from ..services.llm import INTAKE


class OrderIntakeAgent(BaseAgent):
    agent_name = 'OrderIntakeAgent'

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def _build_messages(self, state, ctx) -> list:
        catalog = (f"customers {', '.join(self.catalog.customers)}; "
                   f"products {', '.join(self.catalog.products)}")
        return [{'role': 'system', 'content': f'You are the {INTAKE}. Extract customer_id, sku and quantity '
                                              'as JSON, or list what is missing as {"missing": [...]}.'},
                {'role': 'user', 'content': f"{state['query']}\nCatalog: {catalog}"}]

    def _evaluate_output(self, response, state, ctx) -> float:
        data = None
        try:
            data = json.loads((response or {}).get('text', ''))
            request = OrderRequest.model_validate(data)
        except (ValueError, ValidationError):
            missing = data.get('missing') if isinstance(data, dict) else None
            state['missing'] = missing or ['customer', 'sku', 'quantity']
            return 0.0
        unknown = [v for v, known in ((request.customer_id, self.catalog.customers),
                                      (request.sku, self.catalog.products)) if v not in known]
        if unknown:
            state['missing'] = [f'unknown {v}' for v in unknown]
            return 0.0
        state['order_request'] = request.model_dump()
        return 1.0

    def _fallback(self, state, ctx):
        state['order_request'] = None
        return {'text': 'Please give the customer (CUST-...), the product (SKU-...) and the quantity.',
                'degraded': True}

    def _handle_error(self, error, state, ctx):
        logging.error(f'[{self.agent_name}] {error}')
        state.setdefault('errors', []).append(str(error))
        state['order_request'] = None
