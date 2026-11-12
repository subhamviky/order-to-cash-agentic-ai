"""E2A BaseGovernanceFramework for o2c-agent-service, driven by policies/governance.yaml.

enforce_governance_gate() (inherited, public) runs: capacity admission -> token budget ->
human approval (dehydrates the workflow) -> semantic firewall. redact_response() (inherited,
public) masks the egress. This class supplies only the protected hooks.
"""
import re
import threading
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import yaml
from e2a_base import BaseGovernanceFramework

from ..models.schemas import Approval, OrderRequest
from .stores import ApprovalStore


class GovernancePolicy:
    """policies/governance.yaml, parsed once."""

    def __init__(self, path: Path) -> None:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.entitlements: Dict[str, List[str]] = data["entitlements"]
        self.tools: Dict[str, List[str]] = data["tools"]
        self.approval_threshold = Decimal(data["approval"]["threshold"])
        self.approver_role: str = data["approval"]["approver_role"]
        self.four_eyes: bool = bool(data["approval"]["four_eyes"])
        self.injection = [re.compile(p, re.I) for p in data["firewall"]["injection_patterns"]]
        self.max_query_chars = int(data["firewall"]["max_query_chars"])
        self.redaction = [(r["name"], re.compile(r["pattern"]), r["mask"]) for r in data["redaction"]]
        self.max_inflight = int(data["capacity"]["max_inflight"])
        self.max_token_budget = float(data["capacity"]["max_token_budget"])

    def redact(self, text: str) -> tuple:
        found = []
        for name, pattern, mask in self.redaction:
            text, count = pattern.subn(mask, text)
            if count:
                found.append(name)
        return text, found


class FirewallViolation(PermissionError):
    """The request was refused by the semantic firewall."""


class O2CGovernance(BaseGovernanceFramework):
    def __init__(self, policy: GovernancePolicy, approvals: ApprovalStore) -> None:
        self.policy, self.approvals = policy, approvals
        self.inflight = 0
        self._lock = threading.Lock()

    # Callers bracket a request with these so admission control sees real load.
    def __enter__(self):
        with self._lock:
            self.inflight += 1
        return self

    def __exit__(self, *exc):
        with self._lock:
            self.inflight -= 1

    def _check_execution_capacity(self, state, io_config, config=None, **kwargs) -> bool:
        return self.inflight <= self.policy.max_inflight and self._evaluate_dependency_health(config, **kwargs)

    def _evaluate_dependency_health(self, config=None, **kwargs) -> bool:
        breakers = (config or {}).get("dependency_breakers", [])
        return all(b.state != "OPEN" for b in breakers)

    def _execute_semantic_firewall(self, state, config, **kwargs) -> Dict[str, Any]:
        query = str(state.get("query", ""))
        if len(query) > self.policy.max_query_chars:
            raise FirewallViolation("request too long")
        for pattern in self.policy.injection:
            if pattern.search(query):
                raise FirewallViolation("request refused by the semantic firewall (prompt injection)")
        state["query"], found = self.policy.redact(query)
        if found:
            state["redactions"] = sorted(set(state.get("redactions", [])) | set(found))
        return state

    def _redact_output_fields(self, state, response, config=None, **kwargs) -> Dict[str, Any]:
        if isinstance(response, dict) and isinstance(response.get("text"), str):
            response["text"], _ = self.policy.redact(response["text"])
        return response

    def _verify_sandbox_profile(self, config, **kwargs) -> None:
        if (config or {}).get("require_sandbox") and not (config or {}).get("sandbox_profile"):
            raise PermissionError("MCP tool execution requires a sandboxed runtime")

    def _circuit_breaker(self, failures: int, config, **kwargs) -> bool:
        return failures >= int((config or {}).get("fail_max", 5))

    def _dehydrate_state_to_perimeter(self, state, correlation_id, tenant_id, config) -> None:
        """Persist the paused workflow; it resumes when an approver decides (E2A human-in-the-loop)."""
        snapshot = {k: v for k, v in state.items()
                    if k in ("tenant_id", "user_id", "role", "query", "intent", "order_request", "amount")}
        approval = Approval(approval_id=f"APR-{uuid.uuid4().hex[:10].upper()}", tenant_id=tenant_id,
                            requested_by=state["user_id"], order_request=OrderRequest(**state["order_request"]),
                            amount=Decimal(str(state["amount"])), idempotency_key=state["idempotency_key"],
                            state=snapshot)
        self.approvals.put_new(approval)
        state["approval_id"] = approval.approval_id
