"""E2A BaseWorkflow: one execute() per request. The base owns propagation, the deadline,
the atomic idempotency claim (only for PLACE_ORDER: the one intent with a material
effect), dehydration on human approval, claim settlement by typed outcome (UNKNOWN is
parked for recovery) and the DLQ hand-off. This class supplies the hooks."""
import hashlib
import json
import logging

from e2a_base import BaseWorkflow

REQUIRED = ("PLACE_ORDER", "ORDER_STATUS", "PAYMENT_EXCEPTIONS", "POLICY_QUESTION")


class O2CWorkflow(BaseWorkflow):
    def __init__(self, agents: dict) -> None:
        self.agents = agents                         # intent -> BaseAgent

    def _build_workflow(self, config=None, **kwargs):
        return {"nodes": sorted(self.agents)}

    def _validate_workflow(self, workflow, config=None, **kwargs):
        return all(intent in workflow["nodes"] for intent in REQUIRED)

    def _get_agent(self, intent, config=None, **kwargs):
        if intent not in self.agents:
            raise ValueError(f"no agent for intent {intent}")
        return self.agents[intent]

    def _order_content(self, state) -> str:
        return json.dumps({"tenant": state.get("tenant_id"), "user": state.get("user_id"),
                           "order": state.get("order_request")}, sort_keys=True)

    def _generate_idempotency_key(self, state, config=None, **kwargs) -> str:
        """Without a client Idempotency-Key, the same order by the same user is one order."""
        basis = self._order_content(state) if state.get("intent") == "PLACE_ORDER" else \
            json.dumps([state.get("tenant_id"), state.get("correlation_id")])
        return "o2c-" + hashlib.sha256(basis.encode()).hexdigest()[:32]

    def _requires_idempotency_claim(self, state, config=None, **kwargs) -> bool:
        return state.get("intent") == "PLACE_ORDER"

    def _request_fingerprint(self, state, config=None, **kwargs) -> str:
        """The business content only: an approval resumes the SAME request."""
        return hashlib.sha256(self._order_content(state).encode()).hexdigest()

    def _handle_error(self, error, state, config=None, **kwargs):
        logging.error(f"[O2CWorkflow] {error}")
        state["status"] = "FAILED"
        state.setdefault("errors", []).append(str(error))
