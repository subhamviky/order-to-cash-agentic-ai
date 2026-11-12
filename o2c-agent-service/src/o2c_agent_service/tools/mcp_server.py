"""E2A BaseMCPServer: the read-only O2C tools as an MCP server (JSON-RPC tools/list and
tools/call), so an external agent can use them under the same contract. serve() is
inherited; tools are registered with the inherited wrap_api_as_tool() factory. The only
hook overridden puts the caller's tenant into the arguments, so a tool call is always
scoped to the tenant of the request, never to one the caller names."""
from e2a_base import BaseMCPServer


class O2CMCPServer(BaseMCPServer):
    server_name = "o2c-tools"

    def __init__(self, tools) -> None:
        super().__init__()
        self.wrap_api_as_tool(tools["check_stock"], "check_stock", "Available stock of one SKU",
                              {"type": "object", "required": ["sku"], "properties": {"sku": {"type": "string"}}})
        self.wrap_api_as_tool(tools["get_order"], "get_order", "One order of the caller's tenant",
                              {"type": "object", "required": ["order_id"],
                               "properties": {"order_id": {"type": "string"}}})

    async def _call_tool(self, tool_name, arguments, config=None, tenant_id=None, **kwargs):
        return await super()._call_tool(tool_name, dict(arguments, tenant_id=tenant_id), config,
                                        tenant_id=tenant_id, **kwargs)
