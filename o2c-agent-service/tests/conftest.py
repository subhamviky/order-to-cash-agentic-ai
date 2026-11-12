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
