"""E2A v1.2 governance for o2c-agent-service: ordered stages built from
policies/governance.yaml (E2A design note 04).

enforce_governance_gate() and redact_response() (inherited, public) run the stages. Every
agent of the workflow passes them: the screening stages before it reads anything,
approval once the order is priced, redaction on egress. tool_policy is the per-agent
tool allow-list that E2A applies to each agent's io_read / io_modify. Every refusal is
typed (code, stage, reason, retryable). This class supplies only the policy data.
"""
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import yaml
from e2a import (ApprovalStage, BaseGovernanceFramework, CapacityStage, FirewallStage, GovernanceRefusal,
                 InflightLimiter, IngressStage, RedactionStage, SandboxStage, TokenBudgetStage, compile_redactions,
                 redact_text)

# which agent serves an intent: the entitlement stage checks the caller's role for it
AGENT_FOR = {"PLACE_ORDER": "OrderExecutionAgent", "ORDER_STATUS": "FinanceAgent",
             "PAYMENT_EXCEPTIONS": "FinanceAgent", "POLICY_QUESTION": "KnowledgeAgent"}


class GovernancePolicy:
    """policies/governance.yaml, parsed once."""

    def __init__(self, path: Path) -> None:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.entitlements: Dict[str, List[str]] = data["entitlements"]
        self.tools: Dict[str, List[str]] = data["tools"]
        self.approval_threshold = Decimal(data["approval"]["threshold"])
        self.approver_role: str = data["approval"]["approver_role"]
        self.four_eyes: bool = bool(data["approval"]["four_eyes"])
        self.injection_patterns: List[str] = data["firewall"]["injection_patterns"]
        self.max_query_chars = int(data["firewall"]["max_query_chars"])
        self.redaction = compile_redactions(data["redaction"])
        self.max_inflight = int(data["capacity"]["max_inflight"])
        self.max_token_budget = float(data["capacity"]["max_token_budget"])

    def redact(self, text: str) -> tuple:
        return redact_text(text, self.redaction)


class EntitlementRefusal(GovernanceRefusal, PermissionError):
    code = "ENTITLEMENT"


class EntitlementStage(IngressStage):
    """ABAC: the caller's role must be entitled to the agent that serves the request's
    intent (before routing: the RouterAgent). A viewer asking for an order is refused
    before any order agent, model call or tool is reached."""
    name = "entitlement"

    def __init__(self, policy: GovernancePolicy) -> None:
        self.policy = policy

    def check(self, state, ctx, messages):
        agent = AGENT_FOR.get(state.get("intent"), "RouterAgent")
        if state.get("role") not in self.policy.entitlements.get(agent, []):
            raise EntitlementRefusal(f"role '{state.get('role')}' may not use {agent}", self.name)
        return state


class O2CGovernance(BaseGovernanceFramework):
    def __init__(self, policy: GovernancePolicy, breakers=()) -> None:
        self.policy = policy
        self.limiter = InflightLimiter(policy.max_inflight)       # requests bracket themselves with slot()
        self.breakers = list(breakers)

    @property
    def tool_policy(self) -> Dict[str, List[str]]:
        return self.policy.tools

    @property
    def stages(self) -> list:
        """Built from the policy on every request, so a policy change applies at once."""
        self.limiter.limit = self.policy.max_inflight
        threshold = self.policy.approval_threshold
        return [
            CapacityStage(self.limiter, self.breakers),
            TokenBudgetStage(),                              # ctx.setting('max_token_budget')
            FirewallStage(self.policy.injection_patterns, self.policy.redaction, fields=("query",),
                          max_chars=self.policy.max_query_chars),
            EntitlementStage(self.policy),
            SandboxStage(),
            ApprovalStage(required=lambda state, ctx: Decimal(str(state.get("amount") or 0)) > threshold,
                          reason=f"orders above {threshold} wait for a {self.policy.approver_role}"),
            RedactionStage(self.policy.redaction, fields=("text",)),
        ]
