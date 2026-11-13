"""Several instances on one Firestore (e2a-adapters, design note D-03): what lets Cloud Run run
more than one instance. Needs the Firestore emulator (FIRESTORE_EMULATOR_HOST); skipped otherwise."""
import os
import threading
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("FIRESTORE_EMULATOR_HOST"),
                                reason="FIRESTORE_EMULATOR_HOST not set (Firestore emulator not running)")

from conftest import ask
from o2c_agent_service.services.state import state_ports

LARGE = "Order 4 units of SKU-300 for customer CUST-GLOBEX"        # waits for approval


@pytest.fixture
def two_instances(make_assistant, monkeypatch):
    monkeypatch.setenv("O2C_STATE_BACKEND", "firestore")
    monkeypatch.setenv("O2C_FIRESTORE_COLLECTION", f"o2c-shared-{uuid.uuid4().hex[:10]}")
    env = dict(os.environ)
    return (make_assistant(), make_assistant()) if state_ports(env) else None


def test_an_order_placed_on_one_instance_is_seen_on_the_other(two_instances, settlement):
    a, b = two_instances
    placed = ask(a, "Order 2 units of SKU-100 for customer CUST-ACME", key="k-1")
    assert placed.order.status == "PAID"
    assert b.orders.get("acme", placed.order.order_id).status == "PAID"
    replay = ask(b, "Order 2 units of SKU-100 for customer CUST-ACME", key="k-1")
    assert replay.order.order_id == placed.order.order_id and settlement.posts == 1, \
        "the claim is shared: the second instance replays, it does not charge again"


def test_a_new_instance_does_not_reset_reserved_stock(two_instances, make_assistant):
    a, _ = two_instances
    before = a.inventory.available("SKU-100")
    ask(a, "Order 3 units of SKU-100 for customer CUST-ACME")
    third = make_assistant()                                   # a Cloud Run instance starting later
    assert third.inventory.available("SKU-100") == before - 3


def test_stock_is_never_oversold_across_instances(two_instances):
    a, b = two_instances
    stock = a.inventory.available("SKU-100")
    results = []

    def reserve(inst):
        for _ in range(stock):
            results.append(inst.inventory.reserve("SKU-100", 1))
    threads = [threading.Thread(target=reserve, args=(i,)) for i in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == stock and a.inventory.available("SKU-100") == 0 == b.inventory.available("SKU-100")


def test_an_approval_requested_on_one_instance_is_listed_and_decided_once_on_the_other(two_instances):
    a, b = two_instances
    waiting = ask(a, LARGE)
    assert waiting.status == "AWAITING_APPROVAL"
    assert [x.approval_id for x in b.approvals.list("acme")] == [waiting.approval_id]
    done = b.approve(waiting.approval_id, "acme", "u-approver", "finance-approver")
    assert done.order.status == "PAID"
    with pytest.raises(Exception):
        a.approve(waiting.approval_id, "acme", "u-approver-2", "finance-approver")
    assert [x.status for x in a.approvals.list("acme")] == ["APPROVED"]
