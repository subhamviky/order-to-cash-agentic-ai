"""Where this service keeps its state: E2A's ports, chosen by O2C_STATE_BACKEND.

  memory     (default) E2A's in-memory reference adapters: tests, local runs, one instance
  firestore  e2a-adapters' Firestore adapters (design note D-03): durable, shared by every
             Cloud Run instance, so the service scales beyond one instance

Firestore settings: GOOGLE_CLOUD_PROJECT, O2C_FIRESTORE_DATABASE (default "(default)") and
O2C_FIRESTORE_COLLECTION (default "o2c"). FIRESTORE_EMULATOR_HOST points the client at the
emulator, as for any Firestore client.
"""
import os
from typing import Mapping, Tuple

from e2a import BaseIdempotencyStore, BaseTransactionalStore
from e2a_inmemory_adapters import InMemoryIdempotencyStore, InMemoryTransactionalStore


def state_ports(env: Mapping[str, str] = None) -> Tuple[BaseTransactionalStore, BaseIdempotencyStore]:
    """(rows, claims): the transactional store behind orders, stock and approvals, and the
    idempotency store behind every request's claim."""
    env = os.environ if env is None else env
    backend = env.get("O2C_STATE_BACKEND", "memory")
    if backend == "memory":
        return InMemoryTransactionalStore(), InMemoryIdempotencyStore()
    if backend == "firestore":
        from google.cloud import firestore
        from e2a_adapters.gcp import FirestoreIdempotencyStore, FirestoreTransactionalStore
        client = firestore.Client(project=env.get("GOOGLE_CLOUD_PROJECT"),
                                  database=env.get("O2C_FIRESTORE_DATABASE", "(default)"))
        collection = env.get("O2C_FIRESTORE_COLLECTION", "o2c")
        return FirestoreTransactionalStore(client, collection), FirestoreIdempotencyStore(client, collection)
    raise ValueError(f"O2C_STATE_BACKEND={backend!r}: use 'memory' or 'firestore'")
