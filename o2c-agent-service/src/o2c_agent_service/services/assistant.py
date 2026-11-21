"""The O2C assistant: composition root and the service's four capabilities.

handle():            validate the request, then O2CWorkflow.execute(): route -> (orders:
                     intake) -> the specialist, every step behind the governance stages.
approve() / reject(): a finance approver's decision. O2CWorkflow.resume() continues the
                     paused order at its step, under the same idempotency key, exactly once.
recover_stuck():     the scheduled sweep: every order left unfinished for a while, recovered.
recover():           an unfinished order (payment UNKNOWN, or a saga a crash stopped), through
                     O2CRecovery.reconcile() (E2A BaseReconciliationService).
"""
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from e2a import BrokerOutboxSweeper, CapacityRefusal, ResumeRefused
from e2a.evals import RecordingOnlineEvaluator
from e2a_adapters.workload import workload_credentials
from e2a_simulated_llm import SimulatedLLMService

from ..agents.finance_agent import FinanceAgent
from ..agents.knowledge_agent import KnowledgeAgent
from ..agents.order_execution_agent import OrderExecutionAgent, order_id_for
from ..agents.order_intake_agent import OrderIntakeAgent
from ..agents.router_agent import RouterAgent
from ..models.schemas import AssistantResponse, Order
from ..rag.policy_rag import load_knowledge, policy_rag
from ..tools.local import local_tools
from ..tools.mcp_server import O2CMCPServer
from ..tools.services import reconciliation_tools, settlement_tools
from ..workflow.o2c_workflow import O2CWorkflow
from .catalog import Catalog
from .governance import GovernancePolicy, O2CGovernance
from .recovery import O2CRecovery
from .state import event_ports, events_topic, state_ports
from .stores import FINAL_STATUSES, ApprovalStore, InventoryStore, OrderStore
from .validation import O2CValidationService

HELP = "I can place orders, report an order's payment status, list payment exceptions and answer O2C policy questions."


class Forbidden(Exception):
    """The caller may not do this (HTTP 403)."""


class NotFound(Exception):
    """No such approval or order for this tenant (HTTP 404)."""


class O2CAssistant:
    def __init__(self, service_root: Path, llm: SimulatedLLMService, settlement_url: str,
                 reconciliation_url: str, settlement_transport=None, reconciliation_transport=None,
                 config: Optional[Dict] = None, state=None, events=None) -> None:
        root = Path(service_root)
        self.catalog = Catalog(root / "policies" / "catalog.yaml")
        self.policy = GovernancePolicy(root / "policies" / "governance.yaml")
        self.llm = llm
        rows, claims = state or state_ports()     # (BaseTransactionalStore, BaseIdempotencyStore)
        self.orders, self.approvals = OrderStore(rows, events_topic()), ApprovalStore(rows)
        # order events: committed with each order change, published by this sweeper (services/events.py)
        self.broker, lease = events or event_ports()
        self.events = BrokerOutboxSweeper(rows.outbox, self.broker, lock=lease) if self.orders.emits_events else None
        self.inventory = InventoryStore({sku: p.stock for sku, p in self.catalog.products.items()}, rows)
        self.governance = O2CGovernance(self.policy)
        self.validation = O2CValidationService(self.policy)
        self.store = claims
        self.tools = {**local_tools(self.inventory, self.orders),
                      **settlement_tools(settlement_url, settlement_transport),
                      **reconciliation_tools(reconciliation_url, reconciliation_transport)}
        credentials = workload_credentials()     # SI-01: this service's token to the others; None unless configured
        # EV-01 (E2A v1.9): with O2C_EVAL_RECORDS set, every settled run that E2A samples
        # (ONLINE_EVAL_SAMPLE_RATE, default 0.1) is recorded as a redacted JSON line, off the request path
        records = os.getenv("O2C_EVAL_RECORDS")
        self.config = {"llm_service": llm, "governance_engine": self.governance, "tools": self.tools,
                       **({"credential_provider": credentials} if credentials is not None else {}),
                       **({"online_evaluator": RecordingOnlineEvaluator(records)} if records else {}),
                       "idempotency_store": self.store, "checkpoint_store": self.approvals,
                       "min_confidence": 0.85, "max_latency": 15.0, "timeout": 5.0, "retries": 2, **(config or {})}
        self.mcp = O2CMCPServer(self.tools)

        self.rag = policy_rag()
        report = self.rag.ingest(load_knowledge(root / "knowledge"), self.config, tenant_id=self.catalog.tenant)
        if report["failed_keys"]:
            raise RuntimeError(f"knowledge not indexed: {report['failed_keys']}")

        finance = FinanceAgent()
        self.workflow = O2CWorkflow(self.policy, RouterAgent(), OrderIntakeAgent(self.catalog), {
            "PLACE_ORDER": OrderExecutionAgent(self.catalog, self.orders, self.inventory),
            "ORDER_STATUS": finance, "PAYMENT_EXCEPTIONS": finance,
            "POLICY_QUESTION": KnowledgeAgent(self.rag)})
        self.recovery = O2CRecovery(self.orders, self.inventory, self.catalog, self.policy, self.store)

    # ------------------------------------------------------------------ capabilities
    def handle(self, text: str, tenant_id: str, user_id: str, role: str,
               idempotency_key: Optional[str] = None) -> AssistantResponse:
        return self.handle_traced(text, tenant_id, user_id, role, idempotency_key)[0]

    def handle_traced(self, text: str, tenant_id: str, user_id: str, role: str,
                      idempotency_key: Optional[str] = None) -> Tuple[AssistantResponse, Dict]:
        """handle(), and the workflow's final state: the steps, the tools called (E2A v1.9
        trajectory) and the evaluation. The release gate scores trajectory cases on it."""
        state = {"tenant_id": tenant_id, "user_id": user_id, "role": role, "query": text}
        self._check("RouterAgent", state)
        with self.governance.limiter.slot():
            state = self.workflow.execute(state, self._request_config(), idempotency_key=idempotency_key)
        return self._outcome(state), state

    def approve(self, approval_id: str, tenant_id: str, user_id: str, role: str) -> AssistantResponse:
        state = self._decide(approval_id, tenant_id, {"approved": True, "decided_by": user_id, "role": role})
        return self._outcome(state)

    def reject(self, approval_id: str, tenant_id: str, user_id: str, role: str) -> AssistantResponse:
        self._decide(approval_id, tenant_id, {"approved": False, "decided_by": user_id, "role": role})
        return AssistantResponse(status="COMPLETED", intent="PLACE_ORDER", approval_id=approval_id,
                                 answer=f"Approval {approval_id} rejected; no stock was reserved and no money moved.")

    def recover(self, order_id: str, tenant_id: str) -> Order:
        if self.orders.get(tenant_id, order_id) is None:
            raise NotFound(f"order {order_id}")
        self.recovery.reconcile(self._request_config(), tenant_id=tenant_id, order_id=order_id)
        return self.orders.get(tenant_id, order_id)

    def recover_stuck(self, older_than_seconds: Optional[float] = None) -> Dict:
        """Finish the orders a crash or a lost answer left unfinished (Cloud Scheduler calls this).

        Each order listed open for longer than `older_than_seconds` (O2C_RECOVERY_AFTER_SECONDS,
        default 600: past the idempotency lease) goes through O2CRecovery, which takes over its
        claim only if no live request holds it. An entry whose order is final, or that has no order
        after the same period, is removed."""
        older_than = float(os.getenv("O2C_RECOVERY_AFTER_SECONDS", "600") if older_than_seconds is None
                           else older_than_seconds)
        now = self.orders.open.clock()
        report = {"checked": 0, "finished": [], "still_open": [], "removed": 0}
        for entry, since in self.orders.open.entries().items():
            if now - since < older_than:
                continue
            tenant_id, order_id = entry.split("/", 1)
            report["checked"] += 1
            order = self.orders.get(tenant_id, order_id)
            if order is not None and order.status not in FINAL_STATUSES:
                self.recovery.reconcile(self._request_config(), tenant_id=tenant_id, order_id=order_id)
                order = self.orders.get(tenant_id, order_id)
                if order.status not in FINAL_STATUSES:
                    report["still_open"].append(order_id)
                    continue
                report["finished"].append(order_id)
            self.orders.open.remove(tenant_id, order_id)
            report["removed"] += 1
        return report

    def publish_events(self) -> Dict:
        """Publish the order events committed so far (Cloud Scheduler calls this). One sweeper at
        a time, under a lease; a second caller is told SKIPPED_LOCKED."""
        if self.events is None:
            return {"status": "DISABLED", "published": 0, "failed_keys": []}
        return self.events.sweep(self.config)

    # ------------------------------------------------------------------- helpers
    def _request_config(self) -> Dict:
        """The policy's current token budget: a policy change applies to the next request."""
        return {**self.config, "max_token_budget": self.policy.max_token_budget}

    def _decide(self, approval_id, tenant_id, decision) -> Dict:
        try:
            with self.governance.limiter.slot():
                return self.workflow.resume(approval_id, decision, self._request_config(), tenant_id=tenant_id)
        except ResumeRefused as refused:
            if refused.code == "UNKNOWN_CHECKPOINT":
                raise NotFound(f"approval {approval_id}") from refused
            raise Forbidden(refused.reason) from refused

    def _check(self, agent_name: str, state: Dict) -> None:
        result = self.validation.validate(agent_name, state, self.config)
        if not result["valid"]:
            if result.get("forbidden"):
                raise Forbidden("; ".join(result["errors"]))
            raise ValueError("; ".join(result["errors"]))

    def _outcome(self, state) -> AssistantResponse:
        refusal = state.get("refusal")
        if refusal:                                     # a typed governance refusal
            if refusal["code"] == "ENTITLEMENT":
                raise Forbidden(refusal["reason"])
            if refusal["code"] == "CAPACITY":
                raise CapacityRefusal(refusal["reason"], refusal["stage"])
            if refusal["code"] == "FIREWALL":
                return self._answer(state, "REFUSED", refusal["reason"])
            return self._answer(state, "FAILED", f"The request was not executed ({refusal['reason']}).")
        if state.get("intent", "UNSUPPORTED") == "UNSUPPORTED":
            return self._answer(state, "COMPLETED", HELP)
        if state.get("intent") == "PLACE_ORDER" and not state.get("order_request"):
            return self._answer(state, "NEEDS_CLARIFICATION",
                                "Please give the customer (CUST-...), the product (SKU-...) and the "
                                f"quantity; missing: {', '.join(state.get('missing', []))}.")
        return self._result(state)

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
                                f"(approval {state['checkpoint_id']}). Nothing was reserved or charged yet.",
                                approval_id=state["checkpoint_id"])
        if state.get("errors") and not order:
            status = "FAILED"
        if status == "RECOVERY_REQUIRED" and state.get("intent") == "PLACE_ORDER" and state.get("idempotency_key"):
            order_id = order_id_for(state["idempotency_key"])
            return self._answer(state, status, f"Order {order_id} did not finish (recovery required); it is "
                                               f"finished with POST /api/v1/orders/{order_id}/recover.")
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
