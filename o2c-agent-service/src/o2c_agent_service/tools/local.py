"""Tools implemented in this service: stock and orders. Wrapped as LocalTool so they share
the tool contract, and exposed to external agents over MCP (tools/mcp_server.py)."""
from typing import Dict

from e2a import PhysicalOutcome

from ..services.stores import InventoryStore, OrderStore
from .services import LocalTool


def local_tools(inventory: InventoryStore, orders: OrderStore) -> Dict[str, LocalTool]:
    def check_stock(p):
        return {"physical_success": True, "outcome": PhysicalOutcome.NOT_COMMITTED,   # a read commits nothing
                "sku": p["sku"], "available": inventory.available(p["sku"])}

    def reserve_stock(p):
        ok = inventory.reserve(p["sku"], int(p["quantity"]))
        return {"physical_success": ok,
                "outcome": PhysicalOutcome.COMMITTED if ok else PhysicalOutcome.NOT_COMMITTED}

    def release_stock(p):
        inventory.release(p["sku"], int(p["quantity"]))
        return {"physical_success": True, "outcome": PhysicalOutcome.COMMITTED}

    def get_order(p):
        order = orders.get(p["tenant_id"], p["order_id"])
        return {"physical_success": order is not None, "outcome": PhysicalOutcome.NOT_COMMITTED,
                "order": order.model_dump(mode="json") if order else None}

    return {"check_stock": LocalTool("check_stock", check_stock, ("sku",)),
            "reserve_stock": LocalTool("reserve_stock", reserve_stock, ("sku", "quantity"), material=True),
            "release_stock": LocalTool("release_stock", release_stock, ("sku", "quantity"), material=True),
            "get_order": LocalTool("get_order", get_order, ("order_id",))}
