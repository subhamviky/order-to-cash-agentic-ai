"""Order events (E2A v1.7.3): an order's change and its event commit together, and the
sweeper publishes each event once. In memory, then on the Firestore and Pub/Sub emulators."""
import os
import threading
import uuid

import pytest

from conftest import ask

SMALL = "Order 2 units of SKU-100 for customer CUST-ACME"


@pytest.fixture
def local_events(make_assistant):
    """Assistants whose events go to an in-memory broker, whatever the state backend (the
    Firestore run of the suite keeps its state in Firestore; Pub/Sub is tested below)."""
    from e2a import InMemoryBroker
    from e2a_inmemory_adapters import InMemoryLease

    def make(**config):
        return make_assistant(events=(InMemoryBroker(), InMemoryLease()), **config)
    return make


@pytest.fixture
def assistant(local_events):
    return local_events()


def events(assistant):
    """The events published so far: (event_type, idempotency_key) per message."""
    got = assistant.broker.receive(assistant.orders.topic, max_messages=50)
    return [(m.body["event_type"], m.idempotency_key) for m in got]


def test_a_paid_order_announces_placed_then_paid_once(assistant):
    answer = ask(assistant, SMALL, key="k-1")
    order_id = answer.order.order_id
    assert assistant.publish_events()["published"] == 2
    assert events(assistant) == [("order.placed", f"{order_id}:PENDING_PAYMENT"), ("order.paid", f"{order_id}:PAID")]
    ask(assistant, SMALL, key="k-1")                                  # a replay changes nothing: no event
    assert assistant.publish_events()["published"] == 0 and events(assistant) == []


def test_each_outcome_has_its_event(assistant):
    ask(assistant, "Order 2 units of SKU-100 for customer CUST-HOLD")             # blocked payer
    assistant.inventory.reserve("SKU-200", 200)
    ask(assistant, "Order 2 units of SKU-200 for customer CUST-ACME")             # no stock
    assistant.publish_events()
    kinds = [kind for kind, _ in events(assistant)]
    assert kinds == ["order.placed", "order.cancelled", "order.refused"]


def test_an_event_carries_the_order_and_its_tenant(assistant):
    order_id = ask(assistant, SMALL).order.order_id
    assistant.publish_events()
    [placed, paid] = assistant.broker.receive(assistant.orders.topic, max_messages=10)
    assert paid.tenant_id == "acme" and paid.attributes["order_id"] == order_id
    assert paid.body["amount"] == "240.00" and paid.body["status"] == "PAID" and paid.body["settlement_id"]


def test_a_lost_answer_then_recovery_announces_each_status_once(local_events, settlement):
    assistant = local_events(timeout=0.2)
    settlement.answer_delay = 1.0
    order_id = ask(assistant, SMALL).order.order_id
    settlement.answer_delay = 0.0
    assistant.recover(order_id, "acme")
    assistant.recover(order_id, "acme")                               # already PAID: no second event
    assistant.publish_events()
    assert [k for k, _ in events(assistant)] == ["order.placed", "order.payment_unknown", "order.paid"]


def test_a_store_without_an_outbox_emits_nothing():
    from e2a_inmemory_adapters import InMemoryTransactionalStore
    from o2c_agent_service.services.stores import OrderStore
    assert OrderStore(InMemoryTransactionalStore()).emits_events is False


# ---------------------------------------------------------------- on the emulators
@pytest.mark.skipif(not (os.getenv("FIRESTORE_EMULATOR_HOST") and os.getenv("PUBSUB_EMULATOR_HOST")),
                    reason="FIRESTORE_EMULATOR_HOST and PUBSUB_EMULATOR_HOST not both set")
def test_two_instances_publish_each_event_to_pub_sub_exactly_once(make_assistant, monkeypatch, settlement):
    from google.cloud import pubsub_v1
    project, topic = "demo-o2c", f"o2c-events-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("O2C_STATE_BACKEND", "firestore")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", project)
    monkeypatch.setenv("PUBSUB_TOPIC", topic)
    monkeypatch.setenv("O2C_FIRESTORE_COLLECTION", f"o2c-events-{uuid.uuid4().hex[:8]}")
    publisher, subscriber = pubsub_v1.PublisherClient(), pubsub_v1.SubscriberClient()
    topic_path = publisher.create_topic(name=f"projects/{project}/topics/{topic}").name
    sub_path = subscriber.create_subscription(name=f"projects/{project}/subscriptions/{topic}-sub",
                                              topic=topic_path).name

    a, b = make_assistant(), make_assistant()                        # two Cloud Run instances, one database
    placed = [ask(a, SMALL, key="e-1").order.order_id, ask(b, "Order 1 units of SKU-200 for customer CUST-ACME",
                                                           key="e-2").order.order_id]
    reports = []
    sweepers = [threading.Thread(target=lambda x=x: reports.append(x.publish_events())) for x in (a, b, a, b)]
    for t in sweepers:
        t.start()
    for t in sweepers:
        t.join()
    assert a.publish_events()["published"] == 0                     # nothing left pending

    received = []
    for _ in range(10):
        got = a.broker.receive(f"{topic}-sub", max_messages=50, wait_seconds=1)
        for m in got:
            a.broker.ack(f"{topic}-sub", m)
        received += [m.idempotency_key for m in got]
        if len(received) >= 4:
            break
    expected = {f"{o}:{s}" for o in placed for s in ("PENDING_PAYMENT", "PAID")}
    assert sorted(received) == sorted(expected), (received, reports)  # each event once, none lost
    subscriber.delete_subscription(subscription=sub_path)
    publisher.delete_topic(topic=topic_path)
