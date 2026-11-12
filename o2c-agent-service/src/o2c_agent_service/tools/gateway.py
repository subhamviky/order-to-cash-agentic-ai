"""The only way an agent reaches a tool: per-agent allow-list (governance.yaml), then the
tool's inherited execute(). A transport failure of a MATERIAL call is typed UNKNOWN (the
request may have been committed), never "failed": it is reconciled, not blindly re-sent.
"""
from typing import Any, Dict

from e2a_base import PhysicalOutcome, _run_on_bridge_loop

from ..services.governance import GovernancePolicy


class ToolDenied(PermissionError):
    """The agent is not allowed to use this tool."""


class ToolGateway:
    MATERIAL = {"submit_settlement", "reserve_stock", "release_stock"}

    def __init__(self, policy: GovernancePolicy, tools: Dict[str, Any], config: Dict[str, Any]) -> None:
        self.policy, self.tools, self.config = policy, tools, config

    def call(self, agent_name: str, tool_name: str, payload: Dict[str, Any], tenant_id: str,
             idempotency_key: str = None) -> Dict[str, Any]:
        if tool_name not in self.policy.tools.get(agent_name, []):
            raise ToolDenied(f"{agent_name} may not call {tool_name}")
        kwargs = {"tenant_id": tenant_id}
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key
        else:
            kwargs["safe_to_retry"] = tool_name not in self.MATERIAL
        try:
            result = _run_on_bridge_loop(self.tools[tool_name].execute(dict(payload, tenant_id=tenant_id),
                                                                       self.config, **kwargs),
                                         timeout=float(self.config.get("tool_call_bound_seconds", 30)))
        except (PermissionError, ValueError):
            raise
        except Exception as error:                          # transport failure after retries
            outcome = PhysicalOutcome.UNKNOWN if tool_name in self.MATERIAL else PhysicalOutcome.NOT_COMMITTED
            return {"status": "ERROR", "physical_success": False, "outcome": outcome, "error": str(error)}
        result["outcome"] = PhysicalOutcome(result.get("outcome", PhysicalOutcome.NOT_COMMITTED))
        return result
