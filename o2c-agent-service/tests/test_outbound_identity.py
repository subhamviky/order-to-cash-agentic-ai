"""Hub design note SI-01: calls to settlement-service and to reconciliation's service route carry
o2c-agent-service's own token when a credential provider is bound, and nothing more otherwise."""
from conftest import ask

SMALL = "Order 3 units of SKU-100 for customer CUST-ACME"


class Credentials:
    """Stands for e2a_adapters.workload's provider (a Google ID token exchanged for Entra)."""
    SCOPES = {"http://settlement.test": "api://settlement/.default",
              "http://reconciliation.test": "api://reconciliation/.default"}

    def __init__(self):
        self.targets = []

    def headers(self, target, scope=None, config=None, **kwargs):
        self.targets.append(target)
        for prefix, scope in self.SCOPES.items():
            if str(target).startswith(prefix):
                return {"Authorization": f"Bearer o2c-for-{scope}"}
        return {}


def test_settlement_and_reconciliation_calls_carry_the_token_for_their_target(make_assistant, settlement, reconciliation):
    creds = Credentials()
    assistant = make_assistant(credential_provider=creds)
    assert ask(assistant, SMALL).order.status == "PAID"
    assert settlement.post_headers[0]["authorization"] == "Bearer o2c-for-api://settlement/.default"

    reconciliation.add_case("BANK-1", "UNMATCHED", "no settlement", "INVESTIGATE")
    answer = ask(assistant, "Which payments need attention?", role="finance", user="u-fin")
    assert "BANK-1" in answer.answer
    request = reconciliation.requests[-1]
    assert request.url.path == "/service/v1/exceptions"
    assert request.headers["authorization"] == "Bearer o2c-for-api://reconciliation/.default"
    local = [t for t in list(creds.targets) if str(t).startswith("local://")]
    assert local and all(Credentials().headers(t) == {} for t in local)                  # local tools: no token


def test_without_a_provider_no_authorization_header(assistant, settlement):
    ask(assistant, SMALL)
    assert "authorization" not in settlement.post_headers[0]
