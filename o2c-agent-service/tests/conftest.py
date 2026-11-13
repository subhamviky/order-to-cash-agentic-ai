"""An assistant wired to in-process fakes of settlement-service and reconciliation-service."""
from pathlib import Path

import pytest

from o2c_agent_service.release.fakes import FakeReconciliationService, FakeSettlementService
from o2c_agent_service.services.assistant import O2CAssistant
from o2c_agent_service.services.llm import build_o2c_llm

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settlement():
    return FakeSettlementService()


@pytest.fixture
def reconciliation():
    return FakeReconciliationService()


@pytest.fixture
def make_assistant(settlement, reconciliation):
    def make(llm=None, **config):
        return O2CAssistant(ROOT, llm or build_o2c_llm(), "http://settlement.test", "http://reconciliation.test",
                            settlement.transport(), reconciliation.transport(), config=config)
    return make


@pytest.fixture
def assistant(make_assistant):
    return make_assistant()


def ask(assistant, text, role="sales", user="u-sales", key=None):
    return assistant.handle(text, "acme", user, role, key)


@pytest.fixture(autouse=True)
def no_e2a_v11_adapters():
    """v1.3 preparation (design note V13-01): fail a test that uses E2A's v1.1 adapters, which
    v1.3 removes. The warning is recorded, not raised: BaseAgent.run() would swallow an error."""
    import warnings
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        yield
    legacy = [str(w.message) for w in seen if "removed in v1.3" in str(w.message)]
    assert not legacy, legacy


@pytest.fixture(autouse=True)
def isolated_firestore_collection(monkeypatch):
    """With O2C_STATE_BACKEND=firestore (CI runs the whole suite a second time on the Firestore
    emulator), each test gets its own collection: state is durable, so tests must not share it."""
    import os
    import uuid
    if os.getenv("O2C_STATE_BACKEND") == "firestore":
        monkeypatch.setenv("O2C_FIRESTORE_COLLECTION", f"o2c-test-{uuid.uuid4().hex[:10]}")
    yield
