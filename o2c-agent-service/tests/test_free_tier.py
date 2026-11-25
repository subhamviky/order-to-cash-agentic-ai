"""GCP-01, the free tier: Cloud Run IAM's Google ID token as the caller's identity (E2A v1.11.0),
one scheduler call for both scheduled jobs, and the model chosen by E2A_PROVIDER_PROFILE."""
import base64
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from o2c_agent_service.main import build_app
from o2c_agent_service.services.llm import build_o2c_llm

ORDER = {"text": "Order 4 units of SKU-300 for customer CUST-GLOBEX"}        # waits for approval
SALES, APPROVER, ASSISTANT = ("sales@acme.example", "approver@acme.example",
                              "genai-app@demo.iam.gserviceaccount.com")


def b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def id_token(email, tenant="acme", **extra):
    """What Cloud Run hands the container after IAM verified it (the signature is not read)."""
    payload = {"iss": "https://accounts.google.com", "aud": "https://o2c.a.run.app", "email": email,
               "sub": "1077", **extra}
    return {"Authorization": f"Bearer {b64({'alg': 'RS256'})}.{b64(payload)}.c2ln", "X-Tenant-Id": tenant}


@pytest.fixture
def client(assistant, monkeypatch):
    monkeypatch.setenv("E2A_IDENTITY_SOURCE", "gcp_cloud_run")
    monkeypatch.setenv("E2A_IDENTITY_TRUSTED_ISSUERS", '["https://accounts.google.com"]')
    monkeypatch.setenv("E2A_IDENTITY_TENANTS_FROM_ROLES", "tenant:")
    monkeypatch.setenv("E2A_IDENTITY_SUBJECT_ROLES", json.dumps({
        SALES: ["tenant:acme", "sales"], APPROVER: ["tenant:acme", "finance-approver"],
        ASSISTANT: ["tenant:acme", "tenant:globex", "finance"]}))
    return TestClient(build_app(assistant))


def test_the_caller_is_the_email_cloud_run_verified_acting_in_its_granted_role(client):
    placed = client.post("/api/v1/assistant", headers=id_token(SALES), json=ORDER)
    assert placed.status_code == 200 and placed.json()["status"] == "AWAITING_APPROVAL"
    approval = placed.json()["approval_id"]
    # the requester holds no approver role; the approver does (its first role that is not a tenant grant)
    assert client.post(f"/api/v1/approvals/{approval}/approve", headers=id_token(SALES)).status_code == 403
    done = client.post(f"/api/v1/approvals/{approval}/approve", headers=id_token(APPROVER))
    assert done.status_code == 200 and done.json()["order"]["status"] == "PAID"


def test_tenants_are_granted_not_claimed(client):
    assert client.get("/api/v1/approvals", headers=id_token(SALES, tenant="globex")).status_code == 403
    assert client.get("/api/v1/approvals", headers=id_token(ASSISTANT, tenant="globex")).status_code == 200
    stranger = id_token("someone@else.example")
    assert client.get("/api/v1/approvals", headers=stranger).status_code == 403
    no_tenant = {k: v for k, v in id_token(SALES).items() if k != "X-Tenant-Id"}
    assert client.get("/api/v1/approvals", headers=no_tenant).status_code == 403


def test_without_a_token_or_from_another_issuer_nothing_passes(client):
    assert client.get("/api/v1/approvals", headers={"X-Tenant-Id": "acme", "X-User-Role": "sales"}).status_code == 401
    assert client.get("/api/v1/approvals", headers=id_token(SALES, iss="https://evil.example")).status_code == 403
    assert client.get("/api/v1/approvals", headers={"Authorization": "Bearer nope", "X-Tenant-Id": "acme"}).status_code == 401


def test_one_scheduled_call_publishes_events_and_recovers_orders(assistant, monkeypatch):
    calls = []
    monkeypatch.setattr(assistant, "publish_events", lambda: calls.append("events") or {"published": 0})
    monkeypatch.setattr(assistant, "recover_stuck", lambda: calls.append("recovery") or {"finished": []})
    answer = TestClient(build_app(assistant)).post("/internal/jobs/scheduled")
    assert answer.status_code == 200 and calls == ["events", "recovery"]
    assert answer.json() == {"events": {"published": 0}, "recovery": {"finished": []}}


def test_one_failing_job_does_not_stop_the_other(assistant, monkeypatch):
    def broken():
        raise RuntimeError("Pub/Sub unavailable")
    monkeypatch.setattr(assistant, "publish_events", broken)
    monkeypatch.setattr(assistant, "recover_stuck", lambda: {"finished": []})
    client = TestClient(build_app(assistant))
    answer = client.post("/internal/jobs/scheduled")
    assert answer.status_code == 200 and answer.json()["events"]["error"] == "RuntimeError"
    monkeypatch.setattr(assistant, "recover_stuck", broken)
    assert client.post("/internal/jobs/scheduled").status_code == 500         # nothing done: Scheduler sees it


def test_the_model_is_the_simulated_one_unless_a_profile_is_named(monkeypatch):
    monkeypatch.delenv("E2A_PROVIDER_PROFILE", raising=False)
    assert type(build_o2c_llm()).__name__ == "SimulatedLLMService"
    assert type(build_o2c_llm("simulated")).__name__ == "SimulatedLLMService"

    named = []
    fake = types.ModuleType("e2a_managed")
    fake.bindings_from_profile = lambda profile: named.append(profile) or types.SimpleNamespace(llm_service="gemini")
    monkeypatch.setitem(sys.modules, "e2a_managed", fake)
    monkeypatch.setenv("E2A_PROVIDER_PROFILE", "gemini_api")
    assert build_o2c_llm() == "gemini" and named == ["gemini_api"]
