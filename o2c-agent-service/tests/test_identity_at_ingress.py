"""Identity at ingress (E2A v1.7.4): in Google Cloud the caller is who API Gateway verified, not
what the headers claim. API Gateway's X-Apigateway-Api-Userinfo carries the verified JWT payload."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from o2c_agent_service.main import build_app

ORDER = {"text": "Order 4 units of SKU-300 for customer CUST-GLOBEX"}        # waits for approval


def userinfo(sub, tenant, *roles):
    payload = {"sub": sub, "iss": "https://securetoken.google.com/demo-o2c", "firebase": {"tenant": tenant},
               "roles": list(roles)}
    return {"X-Apigateway-Api-Userinfo": base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")}


@pytest.fixture
def client(assistant, monkeypatch):
    monkeypatch.setenv("E2A_IDENTITY_SOURCE", "gcp_api_gateway")
    return TestClient(build_app(assistant))


def test_the_caller_is_who_the_gateway_verified(client):
    placed = client.post("/api/v1/assistant", headers=userinfo("u-sales", "acme", "sales"), json=ORDER)
    assert placed.status_code == 200 and placed.json()["status"] == "AWAITING_APPROVAL"
    approval = placed.json()["approval_id"]
    # the approver acts in their approver role; the requester cannot approve their own order
    own = client.post(f"/api/v1/approvals/{approval}/approve",
                      headers={**userinfo("u-sales", "acme", "sales", "finance-approver"),
                               "X-User-Role": "finance-approver"})
    assert own.status_code == 403
    done = client.post(f"/api/v1/approvals/{approval}/approve", headers=userinfo("u-boss", "acme", "finance-approver"))
    assert done.status_code == 200 and done.json()["order"]["status"] == "PAID"


def test_headers_alone_are_not_an_identity(client):
    forged = {"X-Tenant-Id": "acme", "X-User-Id": "u-sales", "X-User-Role": "sales"}
    assert client.post("/api/v1/assistant", headers=forged, json=ORDER).status_code == 401
    assert client.get("/api/v1/approvals", headers=forged).status_code == 401


def test_another_tenant_or_an_unheld_role_is_refused(client):
    acme_sales = userinfo("u-sales", "acme", "sales")
    assert client.post("/api/v1/assistant", headers={**acme_sales, "X-Tenant-Id": "globex"},
                       json=ORDER).status_code == 403
    assert client.post("/api/v1/assistant", headers={**acme_sales, "X-User-Role": "finance-approver"},
                       json=ORDER).status_code == 403
    viewer = userinfo("u-view", "acme", "viewer")                  # entitlements still apply to the verified role
    assert client.post("/api/v1/assistant", headers=viewer, json=ORDER).status_code == 403


def test_tenants_see_only_their_own_approvals(client):
    client.post("/api/v1/assistant", headers=userinfo("u-sales", "acme", "sales"), json=ORDER)
    assert len(client.get("/api/v1/approvals", headers=userinfo("u-x", "acme", "viewer")).json()) == 1
    assert client.get("/api/v1/approvals", headers=userinfo("u-y", "globex", "viewer")).json() == []


def test_a_malformed_carrier_is_refused(client):
    assert client.get("/api/v1/approvals", headers={"X-Apigateway-Api-Userinfo": "%%%"}).status_code == 401
