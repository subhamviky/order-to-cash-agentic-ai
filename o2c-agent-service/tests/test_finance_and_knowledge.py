"""Read-side agents: answers come from the systems of record or retrieved policies, and
an answer that is not supported by them is replaced (finance) or declined (knowledge)."""
from e2a_simulated_llm import SimulatedLLMService, always

from conftest import ask


def test_order_status_comes_from_both_systems_of_record(assistant):
    order = ask(assistant, "Order 3 units of SKU-100 for customer CUST-ACME").order
    answer = ask(assistant, f"What is the status of order {order.order_id}?", role="finance")
    assert not answer.degraded and "PAID" in answer.answer
    assert f"Settlement {order.settlement_id} is COMPLETED" in answer.answer


def test_an_unknown_order_is_reported_as_unknown(assistant):
    answer = ask(assistant, "What is the status of order ORD-0000000000?", role="finance")
    assert "does not exist" in answer.answer


def test_an_invented_figure_is_replaced_by_the_facts(make_assistant):
    liar = SimulatedLLMService().add_rule("router", lambda m: "router agent" in m[0]["content"],
                                          '{"intent": "ORDER_STATUS"}')
    liar.add_rule("everything else", always(), "Order ORD-0000000000 is PAID, amount 999.99 EUR.")
    answer = ask(make_assistant(llm=liar), "What is the status of order ORD-0000000000?", role="finance")
    assert answer.degraded and "999.99" not in answer.answer and "does not exist" in answer.answer


def test_payment_exceptions_come_from_reconciliation(assistant, reconciliation):
    reconciliation.add_case("STMT-7", "UNMATCHED", "no open item adds up to the amount", "REQUEST_REMITTANCE")
    answer = ask(assistant, "Which payments need attention?", role="finance")
    assert "STMT-7" in answer.answer and "REQUEST_REMITTANCE" in answer.answer and not answer.degraded


def test_reconciliation_down_is_said_not_guessed(assistant, reconciliation):
    reconciliation.down = True
    answer = ask(assistant, "Which payments need attention?", role="finance")
    assert "did not answer" in answer.answer


def test_policy_answers_cite_the_retrieved_policy(assistant):
    answer = ask(assistant, "Is there a discount for paying early?", role="viewer")
    assert answer.citations == ["POL-TERMS-02"] and "2 %" in answer.answer and not answer.degraded


def test_out_of_scope_questions_are_declined(assistant):
    answer = ask(assistant, "What is the capital of France?", role="viewer")
    assert answer.degraded and answer.citations == [] and "could not find" in answer.answer


def test_an_uncited_answer_is_not_trusted(make_assistant):
    llm = SimulatedLLMService().add_rule("router", lambda m: "router agent" in m[0]["content"],
                                         '{"intent": "POLICY_QUESTION"}')
    llm.add_rule("everything else", always(), "Payment is due within 90 days.")
    answer = ask(make_assistant(llm=llm), "What are our payment terms?", role="viewer")
    assert answer.degraded and "90 days" not in answer.answer
