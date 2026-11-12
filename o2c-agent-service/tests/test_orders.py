"""Order execution: a saga through governed tools, idempotent, with approval and recovery."""
from decimal import Decimal

import pytest

from conftest import ask
from o2c_agent_service.services.assistant import Forbidden

SMALL = "Order 3 units of SKU-100 for customer CUST-ACME"          # 360.00
LARGE = "Order 4 units of SKU-300 for customer CUST-GLOBEX"        # 5,800.00 > approval threshold


def test_small_order_is_paid_once(assistant, settlement):
    answer = ask(assistant, SMALL)
    assert answer.status == "COMPLETED" and answer.order.status == "PAID"
    assert answer.order.amount == Decimal("360.00") and answer.order.settlement_status == "COMPLETED"
    assert assistant.inventory.available("SKU-100") == 47
    assert settlement.balances["ACC-2000"] == Decimal("49640.00") and settlement.posts == 1


def test_the_same_order_again_is_replayed_not_charged_twice(assistant, settlement):
    first = ask(assistant, SMALL)
    again = ask(assistant, SMALL)
    assert again.status == "REPLAYED" and again.order.order_id == first.order.order_id
    assert settlement.posts == 1 and assistant.inventory.available("SKU-100") == 47


def test_one_key_for_two_different_orders_is_a_conflict(assistant, settlement):
    ask(assistant, SMALL, key="client-key-1")
    other = ask(assistant, "Order 5 units of SKU-200 for customer CUST-ACME", key="client-key-1")
    assert other.status == "CONFLICT" and settlement.posts == 1


def test_credit_limit_refuses_before_stock_or_money_moves(assistant, settlement):
    approval = ask(assistant, "Order 14 units of SKU-300 for customer CUST-ACME")   # 20,300 > 20,000 limit
    approved = assistant.approve(approval.approval_id, "acme", "u-approver", "finance-approver")
    assert approved.order.status == "REFUSED" and "credit limit" in approved.order.reason
    assert settlement.posts == 0 and assistant.inventory.available("SKU-300") == 10


def test_out_of_stock_is_refused(assistant, settlement):
    assistant.inventory.reserve("SKU-100", 48)
    answer = ask(assistant, SMALL)
    assert answer.order.status == "REFUSED" and answer.order.reason == "insufficient stock" and settlement.posts == 0


def test_rejected_settlement_releases_the_stock(assistant, settlement):
    answer = ask(assistant, "Order 2 units of SKU-100 for customer CUST-HOLD")
    assert answer.order.status == "CANCELLED" and answer.order.reason == "account blocked by policy"
    assert assistant.inventory.available("SKU-100") == 50
    assert "reservation was released" in answer.answer


def test_large_order_waits_for_a_human_and_four_eyes(assistant, settlement):
    waiting = ask(assistant, LARGE)
    assert waiting.status == "AWAITING_APPROVAL" and waiting.approval_id
    assert settlement.posts == 0 and assistant.inventory.available("SKU-300") == 10
    for user, role in (("u-sales", "finance-approver"), ("u-other", "sales")):   # own order / wrong role
        with pytest.raises(Forbidden):
            assistant.approve(waiting.approval_id, "acme", user, role)
    done = assistant.approve(waiting.approval_id, "acme", "u-approver", "finance-approver")
    assert done.order.status == "PAID" and done.order.approved_by == "u-approver"
    assert assistant.inventory.available("SKU-300") == 6 and settlement.posts == 1
    assert [a.status for a in assistant.approvals.list("acme")] == ["APPROVED"]


def test_a_rejected_approval_moves_nothing(assistant, settlement):
    waiting = ask(assistant, LARGE)
    assistant.reject(waiting.approval_id, "acme", "u-approver", "finance-approver")
    assert settlement.posts == 0 and assistant.inventory.available("SKU-300") == 10


def test_a_failing_settlement_service_is_retried_with_the_same_key(assistant, settlement):
    settlement.fail_next = 1
    answer = ask(assistant, SMALL)
    assert answer.order.status == "PAID" and settlement.posts == 2
    assert settlement.balances["ACC-2000"] == Decimal("49640.00")


def test_a_lost_answer_is_unknown_then_recovered_without_double_charge(make_assistant, settlement):
    assistant = make_assistant(timeout=0.2)
    settlement.answer_delay = 1.0                          # committed, but the answer never arrives in time
    unknown = ask(assistant, SMALL)
    assert unknown.order.status == "PAYMENT_UNKNOWN" and unknown.degraded
    assert ask(assistant, SMALL).status == "RECOVERY_REQUIRED"          # the claim is parked, not re-run
    settlement.answer_delay = 0.0
    recovered = assistant.recover(unknown.order.order_id, "acme")
    assert recovered.status == "PAID"
    assert settlement.balances["ACC-2000"] == Decimal("49640.00")       # charged exactly once
    assert ask(assistant, SMALL).status == "REPLAYED"
