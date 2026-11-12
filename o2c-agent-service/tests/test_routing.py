"""RouterAgent and OrderIntakeAgent: proposals that are checked before they are used."""
import pytest

from conftest import ask


@pytest.mark.parametrize("text, intent", [
    ("Order 2 units of SKU-100 for customer CUST-ACME", "PLACE_ORDER"),
    ("What is the status of order ORD-0123456789?", "ORDER_STATUS"),
    ("Which payments need attention?", "PAYMENT_EXCEPTIONS"),
    ("What are our standard payment terms?", "POLICY_QUESTION"),
    ("tell me a joke", "UNSUPPORTED"),
])
def test_router_classifies_each_intent(assistant, text, intent):
    assert ask(assistant, text).intent == intent


def test_unsupported_requests_get_help_not_an_action(assistant, settlement):
    answer = ask(assistant, "tell me a joke")
    assert answer.status == "COMPLETED" and "I can place orders" in answer.answer and settlement.posts == 0


@pytest.mark.parametrize("text", ["Order some SKU-100 for customer CUST-ACME",
                                  "Order 2 units of SKU-999 for customer CUST-ACME",
                                  "Order 2 units of SKU-100 for customer CUST-NOBODY"])
def test_incomplete_or_unknown_orders_ask_for_clarification(assistant, settlement, text):
    answer = ask(assistant, text)
    assert answer.status == "NEEDS_CLARIFICATION" and answer.order is None and settlement.posts == 0
