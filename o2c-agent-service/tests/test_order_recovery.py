"""A crash anywhere in the order saga leaves an order that recovery finishes: no double
charge, no stock lost or counted twice (backlog O2C G-3; settlement's 409 as UNKNOWN)."""
import time
from decimal import Decimal

import pytest

from conftest import ask

SMALL = "Order 3 units of SKU-100 for customer CUST-ACME"          # 360.00
BLOCKED = "Order 2 units of SKU-100 for customer CUST-HOLD"        # settlement-service rejects the payer


class Crash(BaseException):
    """Stands for the process dying: not an Exception, so no agent or workflow handler catches it."""


def crash_when_order_becomes(assistant, monkeypatch, status):
    """The process dies (a hard kill) just before the order's update to `status` is written: from
    that point nothing more is written, so the request's idempotency claim is not settled either."""
    update, complete, fail = assistant.orders.update, assistant.store.complete, assistant.store.fail

    def revive():                                                    # the next process lives
        monkeypatch.setattr(assistant.orders, "update", update)
        monkeypatch.setattr(assistant.store, "complete", complete)
        monkeypatch.setattr(assistant.store, "fail", fail)

    def dying_update(order):
        if order.status == status:
            monkeypatch.setattr(assistant.store, "complete", lambda *a, **k: None)
            monkeypatch.setattr(assistant.store, "fail", lambda *a, **k: None)
            raise Crash(status)
        update(order)
    monkeypatch.setattr(assistant.orders, "update", dying_update)
    return revive


@pytest.fixture
def short_lease(make_assistant):
    # the crashed request's claim expires after one second, as it would after its lease
    return make_assistant(idempotency_lease_seconds=1)


def crash_then_wait(assistant, text, revive):
    with pytest.raises(Crash):
        ask(assistant, text)
    revive()
    time.sleep(1.1)


def the_order_id(answer):
    return answer.answer.split()[1]


def test_keyed_stock_changes_are_made_once(assistant):
    inv = assistant.inventory
    assert inv.reserve("SKU-100", 5, key="o:reserve") and inv.reserve("SKU-100", 5, key="o:reserve")
    assert inv.available("SKU-100") == 45
    inv.release("SKU-100", 5, key="o:release")
    inv.release("SKU-100", 5, key="o:release")
    assert inv.available("SKU-100") == 50
    inv.forget("SKU-100", "o:reserve", "o:release")
    assert inv.applied("SKU-100") == {}


def test_a_crash_after_the_reservation_is_finished_by_recovery_without_reserving_twice(
        short_lease, settlement, monkeypatch):
    assistant = short_lease
    revive = crash_when_order_becomes(assistant, monkeypatch, "PENDING_PAYMENT")
    crash_then_wait(assistant, SMALL, revive)
    assert assistant.inventory.available("SKU-100") == 47 and settlement.posts == 0

    stuck = ask(assistant, SMALL)
    assert stuck.status == "RECOVERY_REQUIRED" and "/recover" in stuck.answer
    order_id = the_order_id(stuck)
    assert assistant.orders.get("acme", order_id).status == "RESERVING"

    recovered = assistant.recover(order_id, "acme")
    assert recovered.status == "PAID"
    assert assistant.inventory.available("SKU-100") == 47           # reserved once
    assert settlement.balances["ACC-2000"] == Decimal("49640.00")
    assert assistant.inventory.applied("SKU-100") == {}             # keys forgotten once final
    assert ask(assistant, SMALL).status == "REPLAYED"


def test_a_crash_after_the_payment_is_finished_by_recovery_without_charging_twice(
        short_lease, settlement, monkeypatch):
    assistant = short_lease
    revive = crash_when_order_becomes(assistant, monkeypatch, "PAID")
    crash_then_wait(assistant, SMALL, revive)
    assert settlement.balances["ACC-2000"] == Decimal("49640.00")   # the money moved before the crash

    order_id = the_order_id(ask(assistant, SMALL))
    assert assistant.orders.get("acme", order_id).status == "PENDING_PAYMENT"
    assert assistant.recover(order_id, "acme").status == "PAID"
    assert settlement.balances["ACC-2000"] == Decimal("49640.00")   # charged once
    assert assistant.inventory.available("SKU-100") == 47


def test_a_crash_after_the_release_is_finished_by_recovery_without_releasing_twice(
        short_lease, settlement, monkeypatch):
    assistant = short_lease
    revive = crash_when_order_becomes(assistant, monkeypatch, "CANCELLED")
    crash_then_wait(assistant, BLOCKED, revive)
    assert assistant.inventory.available("SKU-100") == 50           # released before the crash

    order_id = the_order_id(ask(assistant, BLOCKED))
    recovered = assistant.recover(order_id, "acme")
    assert recovered.status == "CANCELLED"
    assert assistant.inventory.available("SKU-100") == 50           # released once, not 52
    assert assistant.inventory.applied("SKU-100") == {}


def test_recovery_leaves_an_order_alone_while_its_request_holds_the_claim(assistant, settlement, monkeypatch):
    from o2c_agent_service.agents.order_execution_agent import order_id_for
    revive = crash_when_order_becomes(assistant, monkeypatch, "PENDING_PAYMENT")
    with pytest.raises(Crash):
        ask(assistant, SMALL, key="live-key")                       # default lease: the claim is still live
    revive()
    assert ask(assistant, SMALL, key="live-key").status == "IN_PROGRESS"
    order_id = order_id_for("live-key")
    assistant.recover(order_id, "acme")                             # must not take over a live claim
    assert assistant.orders.get("acme", order_id).status == "RESERVING" and settlement.posts == 0


def test_settlement_in_progress_409_is_unknown_not_a_decline(make_assistant, settlement):
    assistant = make_assistant()
    settlement.in_progress_next = 1                                 # 409 is not retried: it is not a 5xx
    unknown = ask(assistant, SMALL)
    assert unknown.order.status == "PAYMENT_UNKNOWN"                # not CANCELLED
    assert assistant.inventory.available("SKU-100") == 47           # the stock stays reserved
    recovered = assistant.recover(unknown.order.order_id, "acme")
    assert recovered.status == "PAID" and settlement.balances["ACC-2000"] == Decimal("49640.00")
