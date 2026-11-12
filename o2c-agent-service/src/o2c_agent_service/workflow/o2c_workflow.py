"""E2A BaseWorkflow (v1.2): one execute() per request, declared as steps (E2A design note 05).

    route   RouterAgent                                   stops when the intent is UNSUPPORTED
    intake  OrderIntakeAgent   only for PLACE_ORDER       stops when the order is incomplete
    act     by intent: OrderExecutionAgent | FinanceAgent | KnowledgeAgent      (material)

The base runs all steps under one context, deadline, log and ONE idempotency claim, taken
before the material step, and only for PLACE_ORDER. A step paused for approval is stored
as a checkpoint (the ApprovalStore); resume() continues at that step once a finance
approver decides, under the same idempotency key. This class supplies the steps and the
domain hooks: the order's key and fingerprint, and who may decide.
"""
import hashlib
import json
import logging

from e2a import BaseWorkflow, ResumeRefused, Route, Step, Steps

from ..services.governance import GovernancePolicy


class O2CWorkflow(BaseWorkflow):
    def __init__(self, policy: GovernancePolicy, router, intake, specialists: dict) -> None:
        self.policy, self.router, self.intake, self.specialists = policy, router, intake, specialists

    def _build_workflow(self, ctx):
        return Steps(
            Step("route", self.router, stop_if=lambda s: s.get("intent") == "UNSUPPORTED"),
            Step("intake", self.intake, when=lambda s: s.get("intent") == "PLACE_ORDER",
                 stop_if=lambda s: not s.get("order_request")),
            Route("act", by="intent", agents=self.specialists, material=True),
        )

    def _order_content(self, state) -> str:
        return json.dumps({"tenant": state.get("tenant_id"), "user": state.get("user_id"),
                           "order": state.get("order_request")}, sort_keys=True)

    def _generate_idempotency_key(self, state, ctx) -> str:
        """Without a client Idempotency-Key, the same order by the same user is one order."""
        basis = self._order_content(state) if state.get("intent") == "PLACE_ORDER" else \
            json.dumps([ctx.tenant_id, ctx.correlation_id])
        return "o2c-" + hashlib.sha256(basis.encode()).hexdigest()[:32]

    def _requires_idempotency_claim(self, state, ctx) -> bool:
        return state.get("intent") == "PLACE_ORDER"

    def _request_fingerprint(self, state, ctx) -> str:
        """The business content only."""
        return hashlib.sha256(self._order_content(state).encode()).hexdigest()

    def _authorize_decision(self, checkpoint, decision, ctx) -> bool:
        """Only a finance approver decides, and never on their own order (four eyes)."""
        if decision.get("role") != self.policy.approver_role:
            raise ResumeRefused(f"only role '{self.policy.approver_role}' may decide approvals", "resume",
                                code="DECIDER_REFUSED")
        if self.policy.four_eyes and decision.get("decided_by") == checkpoint.get("requested_by"):
            raise ResumeRefused("four-eyes principle: the requester cannot approve their own order", "resume",
                                code="DECIDER_REFUSED")
        return True

    def _handle_error(self, error, state, ctx):
        logging.error(f"[O2CWorkflow] {error}")
        state["status"] = "FAILED"
        state.setdefault("errors", []).append(str(error))
