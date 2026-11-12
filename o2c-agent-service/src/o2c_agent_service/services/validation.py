"""E2A BaseValidationService: schema checks per agent, then the entitlement (ABAC) gate.

validate() (inherited, public) resolves the validator registered for the agent, runs it,
and only then calls _enforce_entitlement_gate with the roles from governance.yaml.
"""
import re

from e2a_base import BaseValidationService, ValidationResult

from .governance import GovernancePolicy

TENANT = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


class O2CValidationService(BaseValidationService):
    def __init__(self, policy: GovernancePolicy) -> None:
        self.policy = policy
        self.validator_registry = {
            "RouterAgent": self._validate_request,
            "OrderExecutionAgent": self._validate_request,
            "FinanceAgent": self._validate_request,
            "KnowledgeAgent": self._validate_request,
        }

    def _validate_request(self, state, config=None, **kwargs):
        errors = []
        if not TENANT.match(str(state.get("tenant_id") or "")):
            errors.append("X-Tenant-Id is missing or invalid")
        if not state.get("user_id"):
            errors.append("X-User-Id is required")
        if not state.get("role"):
            errors.append("X-User-Role is required")
        if not str(state.get("query") or "").strip():
            errors.append("text is required")
        return not errors, errors

    def _enforce_entitlement_gate(self, agent_name, state, config=None, **kwargs) -> ValidationResult:
        allowed = self.policy.entitlements.get(agent_name, [])
        if state.get("role") in allowed:
            return ValidationResult(valid=True, errors=[], agent_name=agent_name,
                                    correlation_id=state.get("correlation_id"))
        return ValidationResult(valid=False, forbidden=True, agent_name=agent_name,
                                correlation_id=state.get("correlation_id"),
                                errors=[f"role '{state.get('role')}' may not use {agent_name}"])
