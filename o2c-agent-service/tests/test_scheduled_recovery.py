"""Design document G-2: the scheduled sweep finds and finishes the orders a crash or a lost
answer left unfinished, without waiting for anyone to ask, and leaves live requests alone."""
from decimal import Decimal

import pytest

from conftest import ask
from test_order_recovery import SMALL, Crash, crash_then_wait, crash_when_order_becomes


def test_paid_and_refused_orders_are_never_listed_as_open(assistant):
    assert ask(assistant, SMALL).order.status == "PAID"
    ask(assistant, "Order 14 units of SKU-300 for customer CUST-ACME")        # waits for approval: no order yet
    assert assistant.orders.open.entries() == {}


def test_the_sweep_finishes_an_order_a_crash_left_reserving(make_assistant, settlement, monkeypatch):
    assistant = make_assistant(idempotency_lease_seconds=1)
    revive = crash_when_order_becomes(assistant, monkeypatch, "PENDING_PAYMENT")
    crash_then_wait(assistant, SMALL, revive)
    assert len(assistant.orders.open.entries()) == 1

    report = assistant.recover_stuck(older_than_seconds=0)
    assert len(report["finished"]) == 1 and report["still_open"] == []
    order = assistant.orders.get("acme", report["finished"][0])
    assert order.status == "PAID" and settlement.balances["ACC-2000"] == Decimal("49640.00")
    assert assistant.inventory.available("SKU-100") == 47
    assert assistant.orders.open.entries() == {}
    assert ask(assistant, SMALL).status == "REPLAYED"


def test_the_sweep_finishes_a_lost_answer_once_settlement_answers(make_assistant, settlement):
    assistant = make_assistant(timeout=0.2)
    settlement.answer_delay = 1.0
    unknown = ask(assistant, SMALL)
    assert unknown.order.status == "PAYMENT_UNKNOWN"
    settlement.answer_delay = 0.0
    report = assistant.recover_stuck(older_than_seconds=0)
    assert report["finished"] == [unknown.order.order_id]
    assert settlement.balances["ACC-2000"] == Decimal("49640.00")              # charged once


def test_young_entries_and_live_requests_are_left_alone(assistant, settlement, monkeypatch):
    revive = crash_when_order_becomes(assistant, monkeypatch, "PENDING_PAYMENT")
    with pytest.raises(Crash):
        ask(assistant, SMALL)                                                  # default lease: still live
    revive()
    assert assistant.recover_stuck()["checked"] == 0                          # younger than 600 s
    report = assistant.recover_stuck(older_than_seconds=0)
    assert report["still_open"] and settlement.posts == 0                     # the live claim is not taken over
    assert len(assistant.orders.open.entries()) == 1


def test_an_entry_without_an_order_is_dropped_after_the_period(assistant):
    assistant.orders.open.add("acme", "ORD-GHOST")                             # a crash between listing and creating
    assert assistant.recover_stuck(older_than_seconds=0)["removed"] == 1
    assert assistant.orders.open.entries() == {}


def test_the_endpoint(assistant):
    from fastapi.testclient import TestClient
    from o2c_agent_service.main import build_app
    response = TestClient(build_app(assistant)).post("/internal/orders/recover")
    assert response.status_code == 200 and response.json()["checked"] == 0
