"""HTTP surface, MCP server, and the AI-DLC release gate."""
import json

from fastapi.testclient import TestClient

from o2c_agent_service.main import build_app
from o2c_agent_service.release.gate import O2CReleaseGate

H = {"X-Tenant-Id": "acme", "X-User-Id": "u-sales", "X-User-Role": "sales"}


def test_order_and_approval_over_http(assistant):
    client = TestClient(build_app(assistant))
    paid = client.post("/api/v1/assistant", headers=H,
                       json={"text": "Order 3 units of SKU-100 for customer CUST-ACME"}).json()
    assert client.get(f"/api/v1/orders/{paid['order']['order_id']}", headers=H).json()["status"] == "PAID"
    waiting = client.post("/api/v1/assistant", headers=H,
                          json={"text": "Order 4 units of SKU-300 for customer CUST-GLOBEX"}).json()
    assert [a["approval_id"] for a in client.get("/api/v1/approvals?status=PENDING", headers=H).json()] \
        == [waiting["approval_id"]]
    own = client.post(f"/api/v1/approvals/{waiting['approval_id']}/approve",
                      headers={**H, "X-User-Role": "finance-approver"})
    assert own.status_code == 403
    done = client.post(f"/api/v1/approvals/{waiting['approval_id']}/approve",
                       headers={**H, "X-User-Id": "u-approver", "X-User-Role": "finance-approver"}).json()
    assert done["order"]["status"] == "PAID"
    assert client.get("/api/v1/usage").json()["calls"] > 0


def test_http_errors(assistant):
    client = TestClient(build_app(assistant))
    assert client.post("/api/v1/assistant", json={"text": "hi"}).status_code == 400
    viewer = {**H, "X-User-Role": "viewer"}
    assert client.post("/api/v1/assistant", headers=viewer,
                       json={"text": "Order 2 units of SKU-100 for customer CUST-ACME"}).status_code == 403
    assert client.get("/api/v1/orders/ORD-NONE", headers=H).status_code == 404


def test_mcp_lists_and_calls_tools(assistant):
    client = TestClient(build_app(assistant))
    listed = client.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    assert {t["name"] for t in listed["result"]} == {"check_stock", "get_order"}
    called = client.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                  "params": {"name": "check_stock", "arguments": {"sku": "SKU-200"}}})
    assert "'available': 200" in called.json()["result"]["content"][0]["text"]


def test_release_gate_passes_every_stage():
    gate = O2CReleaseGate(run_tests=False)
    report = gate.run_pipeline({"fleet_replica_count": 1})
    assert report["status"] == "SUCCESS" and report["rag_eval_score"] == 1.0
    assert len(report["stages"]) == 7


def test_release_gate_stops_at_a_leaked_secret_and_an_entry_point_override(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leak.py").write_text('KEY = "AKIA' + "ABCDEFGHIJKLMNOP" + '"\n')
    report = O2CReleaseGate(tmp_path, run_tests=False).run_pipeline({})
    assert report["status"] == "FAILED" and "Static security" in report["error"]
    (tmp_path / "src" / "leak.py").write_text(
        "from e2a_base import BaseAgent\nclass Bad(BaseAgent):\n    def run(self, state):\n        return state\n")
    report = O2CReleaseGate(tmp_path, run_tests=False).run_pipeline({})
    assert report["status"] == "FAILED" and "Single Public Entry Point" in report["error"]
    assert json.dumps(report, default=str)
