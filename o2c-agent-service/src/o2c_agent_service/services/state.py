"""Where this service keeps its state: E2A's ports, chosen by O2C_STATE_BACKEND.

  memory     (default) E2A's in-memory reference adapters: tests, local runs, one instance
  firestore  e2a-adapters' Firestore adapters (design note D-03): durable, shared by every
             Cloud Run instance, so the service scales beyond one instance

Firestore settings: GOOGLE_CLOUD_PROJECT, O2C_FIRESTORE_DATABASE (default "(default)") and
O2C_FIRESTORE_COLLECTION (default "o2c"). FIRESTORE_EMULATOR_HOST points the client at the
emulator, as for any Firestore client.

Order events (E2A v1.7.3): the transactional store has an outbox in the same database, so an
order's row and its event commit together. event_ports() gives what publishes them: the
broker (Pub/Sub on Firestore, PUBSUB_EMULATOR_HOST selecting the emulator; in memory
otherwise) and the lease that keeps one sweeper at a time. PUBSUB_TOPIC names the topic.
"""
import os
from typing import Mapping, Tuple

from e2a import (BaseDistributedLock, BaseIdempotencyStore, BaseMessageBroker, BaseTransactionalStore,
                 InMemoryBroker, InMemoryOutboxStore)
from e2a_inmemory_adapters import InMemoryIdempotencyStore, InMemoryLease, InMemoryTransactionalStore

from .events import DEFAULT_TOPIC


def _backend(env: Mapping[str, str]) -> str:
    backend = env.get("O2C_STATE_BACKEND", "memory")
    if backend not in ("memory", "firestore"):
        raise ValueError(f"O2C_STATE_BACKEND={backend!r}: use 'memory' or 'firestore'")
    return backend


def _firestore(env: Mapping[str, str]):
    from google.cloud import firestore
    client = firestore.Client(project=env.get("GOOGLE_CLOUD_PROJECT"),
                              database=env.get("O2C_FIRESTORE_DATABASE", "(default)"))
    return client, env.get("O2C_FIRESTORE_COLLECTION", "o2c")


def state_ports(env: Mapping[str, str] = None) -> Tuple[BaseTransactionalStore, BaseIdempotencyStore]:
    """(rows, claims): the transactional store behind orders, stock and approvals (with its
    outbox, rows.outbox), and the idempotency store behind every request's claim."""
    env = os.environ if env is None else env
    if _backend(env) == "memory":
        return InMemoryTransactionalStore(outbox=InMemoryOutboxStore()), InMemoryIdempotencyStore()
    from e2a_adapters.gcp import FirestoreIdempotencyStore, FirestoreOutboxStore, FirestoreTransactionalStore
    client, collection = _firestore(env)
    outbox = FirestoreOutboxStore(client, collection, "order-events")
    return (FirestoreTransactionalStore(client, collection, outbox=outbox),
            FirestoreIdempotencyStore(client, collection))


def events_topic(env: Mapping[str, str] = None) -> str:
    env = os.environ if env is None else env
    return env.get("PUBSUB_TOPIC") or DEFAULT_TOPIC


def event_ports(env: Mapping[str, str] = None) -> Tuple[BaseMessageBroker, BaseDistributedLock]:
    """(broker, lease) for the sweeper that publishes order events."""
    env = os.environ if env is None else env
    if _backend(env) == "memory":
        return InMemoryBroker(), InMemoryLease()
    from e2a_adapters.gcp import FirestoreLease, PubSubBroker
    client, collection = _firestore(env)
    return PubSubBroker(env.get("GOOGLE_CLOUD_PROJECT")), FirestoreLease(client, collection)
