"""The O2C assistant: composition root and request flow.

handle(): validate -> ingress governance (capacity, token budget, firewall, PII redaction)
-> RouterAgent -> entitlement gate for the chosen specialist -> (orders: OrderIntakeAgent)
-> O2CWorkflow.execute() -> answer, redacted on egress.
approve()/reject(): the human decision that resumes or ends a dehydrated order.
recover(): resolves an order whose payment outcome is UNKNOWN by re-sending the SAME
idempotency key to settlement-service, which returns the original result.
"""
import uuid
from pathlib import Path
from typing import Dict, Optional

from e2a_base import PhysicalOutcome
from e2a_inmemory_adapters import InMemoryIdempotencyStore
from e2a_simulated_llm import SimulatedLLMService

from ..agents.finance_agent import FinanceAgent
from ..agents.knowledge_agent import KnowledgeAgent
from ..agents.order_execution_agent import OrderExecutionAgent, apply_settlement_result
from ..agents.order_intake_agent import OrderIntakeAgent
from ..agents.router_agent import RouterAgent
from ..models.schemas import AssistantResponse, Order
from ..rag.policy_rag import PolicyIndex, PolicyIndexingPipeline, PolicyRAGPipeline, load_knowledge
from ..tools.gateway import ToolGateway
from ..tools.local import local_tools
from ..tools.mcp_server import O2CMCPServer
from ..tools.services import reconciliation_tools, settlement_tools
from ..workflow.o2c_workflow import O2CWorkflow
from .catalog import Catalog
from .governance import FirewallViolation, GovernancePolicy, O2CGovernance
from .stores import ApprovalStore, InventoryStore, OrderStore
from .validation import O2CValidationService

AGENT_FOR = {"PLACE_ORDER": "OrderExecutionAgent", "ORDER_STATUS": "FinanceAgent",
             "PAYMENT_EXCEPTIONS": "FinanceAgent", "POLICY_QUESTION": "KnowledgeAgent"}
HELP = "I can place orders, report an order's payment status, list payment exceptions and answer O2C policy questions."


class Forbidden(Exception):
    """The caller may not do this (HTTP 403)."""


class NotFound(Exception):
    """No such approval or order for this tenant (HTTP 404)."""


class O2CAssistant:
    def __init__(self, service_root: Path, llm: SimulatedLLMService, settlement_url: str,
                 reconciliation_url: str, settlement_transport=None, reconciliation_transport=None,
                 config: Optional[Dict] = None) -> None:
        root = Path(service_root)
        self.catalog = Catalog(root / "policies" / "catalog.yaml")
        self.policy = GovernancePolicy(root / "policies" / "governance.yaml")
        self.llm = llm
        self.orders, self.approvals = OrderStore(), ApprovalStore()
        self.inventory = InventoryStore({sku: p.stock for sku, p in self.catalog.products.items()})
        self.governance = O2CGovernance(self.policy, self.approvals)
        self.validation = O2CValidationService(self.policy)
        self.store = InMemoryIdempotencyStore()
        self.config = {"llm_service": llm, "idempotency_store": self.store, "min_confidence": 0.85,
                       "max_latency": 15.0, "timeout": 5.0, "retries": 2, **(config or {})}
        tools = {**local_tools(self.inventory, self.orders),
                 **settlement_tools(settlement_url, settlement_transport),
                 **reconciliation_tools(reconciliation_url, reconciliation_transport)}
        self.config["dependency_breakers"] = []
        self.tools = ToolGateway(self.policy, tools, self.config)
        self.mcp = O2CMCPServer(tools)

        index = PolicyIndex()
        report = PolicyIndexingPipeline(index).ingest(load_knowledge(root / "knowledge"), self.config,
                                                      tenant_id=self.catalog.tenant)
        if report["failed_keys"]:
            raise RuntimeError(f"knowledge not indexed: {report['failed_keys']}")
        self.rag = PolicyRAGPipeline(index)

        self.router, self.intake = RouterAgent(), OrderIntakeAgent(self.catalog)
        finance = FinanceAgent(self.tools)
        self.workflow = O2CWorkflow({
            "PLACE_ORDER": OrderExecutionAgent(self.catalog, self.orders, self.tools, self.governance),
            "ORDER_STATUS": finance, "PAYMENT_EXCEPTIONS": finance,
            "POLICY_QUESTION": KnowledgeAgent(self.rag)})

    # ------------------------------------------------------------------ requests
    def handle(self, text: str, tenant_id: str, user_id: str, role: str,
               idempotency_key: Optional[str] = None) -> AssistantResponse:
        state = {"tenant_id": tenant_id, "user_id": user_id, "role": role, "query": text,
                 "correlation_id": str(uuid.uuid4())}
        self._check("RouterAgent", state)
        with self.governance:
            try:
                self.governance.enforce_governance_gate(state, self._io(), self.config,
                                                        correlation_id=state["correlation_id"], tenant_id=tenant_id)
            except FirewallViolation as refused:
                return self._answer(state, "REFUSED", str(refused))
            self.router.run(state, self.config)
            intent = state.get("intent", "UNSUPPORTED")
            if intent == "UNSUPPORTED":
                return self._answer(state, "COMPLETED", HELP)
            self._check(AGENT_FOR[intent], state)
            if intent == "PLACE_ORDER":
                self.intake.run(state, self.config)
                if not state.get("order_request"):
                    return self._answer(state, "NEEDS_CLARIFICATION",
                                        "Please give the customer (CUST-...), the product (SKU-...) and the "
                                        f"quantity; missing: {', '.join(state.get('missing', []))}.")
            if idempotency_key:          # a client key travels in the state: execute() passes its
                state["idempotency_key"] = idempotency_key   # kwargs on to agent.run() as well
            return self._result(self.workflow.execute(state, self.config))

    def approve(self, approval_id: str, tenant_id: str, user_id: str, role: str) -> AssistantResponse:
        approval = self._pending(approval_id, tenant_id, user_id, role)
        approval.status, approval.decided_by = "APPROVED", user_id
        if not self.approvals.decide(approval):
            raise Forbidden("the approval was decided concurrently")
        state = dict(approval.state, approval_granted=True, approved_by=user_id,
                     correlation_id=str(uuid.uuid4()), idempotency_key=approval.idempotency_key)
        with self.governance:
            return self._result(self.workflow.execute(state, self.config))

    def reject(self, approval_id: str, tenant_id: str, user_id: str, role: str) -> AssistantResponse:
        approval = self._pending(approval_id, tenant_id, user_id, role)
        approval.status, approval.decided_by = "REJECTED", user_id
        if not self.approvals.decide(approval):
            raise Forbidden("the approval was decided concurrently")
        return AssistantResponse(status="COMPLETED", intent="PLACE_ORDER", approval_id=approval_id,
                                 answer=f"Approval {approval_id} rejected; no stock was reserved and no money moved.")

    def recover(self, order_id: str, tenant_id: str) -> Order:
        order = self.orders.get(tenant_id, order_id)
        if order is None:
            raise NotFound(f"order {order_id}")
        if order.status != "PAYMENT_UNKNOWN":
            return order
        owner = str(uuid.uuid4())
        claim = self.store.claim(order.idempotency_key, self.config, tenant_id=tenant_id, owner=owner, recover=True)
        customer = self.catalog.customers[order.customer_id]
        result = self.tools.call("OrderExecutionAgent", "submit_settlement", {"json": {
            "payerAccount": customer.payer_account, "payeeAccount": self.catalog.receivable_account,
            "amount": str(order.amount), "currency": order.currency}}, tenant_id, idempotency_key=order.order_id)
        apply_settlement_result(order, result, self.tools, "OrderExecutionAgent", tenant_id)
        self.orders.update(order)
        if claim.owner and result["outcome"] != PhysicalOutcome.UNKNOWN:
            self.store.complete(order.idempotency_key, {"response": {"order": order.model_dump(mode="json")},
                                                        "outcome": result["outcome"].value},
                                self.config, tenant_id=tenant_id, owner=owner)
        return order

    # ------------------------------------------------------------------- helpers
    def _io(self) -> Dict:
        return {"max_token_budget": self.policy.max_token_budget}

    def _check(self, agent_name: str, state: Dict) -> None:
        result = self.validation.validate(agent_name, state, self.config)
        if not result["valid"]:
            if result.get("forbidden"):
                raise Forbidden("; ".join(result["errors"]))
            raise ValueError("; ".join(result["errors"]))

    def _pending(self, approval_id, tenant_id, user_id, role):
        approval = self.approvals.get(tenant_id, approval_id)
        if approval is None:
            raise NotFound(f"approval {approval_id}")
        if role != self.policy.approver_role:
            raise Forbidden(f"only role '{self.policy.approver_role}' may decide approvals")
        if self.policy.four_eyes and user_id == approval.requested_by:
            raise Forbidden("four-eyes principle: the requester cannot approve their own order")
        if approval.status != "PENDING":
            raise Forbidden(f"approval {approval_id} is already {approval.status}")
        return approval

    def _answer(self, state, status, text, **fields) -> AssistantResponse:
        redacted = self.governance.redact_response(state, {"text": text}, self.config)["text"]
        return AssistantResponse(status=status, intent=state.get("intent"), answer=redacted,
                                 correlation_id=state.get("correlation_id"), **fields)

    def _result(self, state) -> AssistantResponse:
        status = state.get("status")
        response = state.get("response") or {}
        order = response.get("order") if isinstance(response, dict) else None
        degraded = bool(isinstance(response, dict) and response.get("degraded"))
        if status == "AWAITING_WEBHOOK":
            return self._answer(state, "AWAITING_APPROVAL",
                                f"The order amounts to {state['amount']} EUR, above the approval threshold of "
                                f"{self.policy.approval_threshold} EUR; it waits for a finance approver "
                                f"(approval {state['approval_id']}). Nothing was reserved or charged yet.",
                                approval_id=state["approval_id"])
        if state.get("errors") and not order:
            status = "FAILED"
        if status in ("CONFLICT", "IN_PROGRESS", "RECOVERY_REQUIRED", "FAILED_FINAL", "FAILED"):
            return self._answer(state, status, f"The request was not executed ({status.lower().replace('_', ' ')}).")
        if order:
            return self._answer(state, "REPLAYED" if state.get("replayed") else "COMPLETED",
                                order_text(Order.model_validate(order)), order=order, degraded=degraded)
        return self._answer(state, "COMPLETED", response.get("text", ""), degraded=degraded,
                            citations=state.get("citations", []))


def order_text(order: Order) -> str:
    what = f"{order.quantity} x {order.sku} for {order.customer_id}, {order.amount} {order.currency}"
    if order.status == "PAID":
        return f"Order {order.order_id} placed: {what}, paid (settlement {order.settlement_id})."
    if order.status == "CANCELLED":
        return (f"Order {order.order_id} was not placed: the payment was {order.settlement_status or 'refused'} "
                f"({order.reason}). The stock reservation was released.")
    if order.status == "REFUSED":
        return f"Order {order.order_id} was refused: {order.reason}."
    return (f"Order {order.order_id} ({what}): the payment outcome is unknown. It will be recovered with the "
            "same idempotency key, so it can never be charged twice.")
