"""The approvals index is paged, so it never outgrows one Firestore document."""
import threading

from e2a_inmemory_adapters import InMemoryTransactionalStore

from o2c_agent_service.services.paged_index import PagedIndex
from o2c_agent_service.services.state import state_ports


def test_pages_roll_over_and_keep_the_order():
    rows = InMemoryTransactionalStore()
    index = PagedIndex(rows, "approvals:acme", page_size=10)
    for i in range(25):
        index.append(f"a{i}")
    assert index.ids() == [f"a{i}" for i in range(25)] and rows.get("approvals:acme:head") == {"pages": 3}


def test_concurrent_appends_lose_nothing():
    """On the configured store: in memory, or on Firestore when the suite runs there."""
    rows, _ = state_ports()
    index = PagedIndex(rows, "approvals:race", page_size=7)

    def append(worker):
        for i in range(15):
            index.append(f"w{worker}-{i}")
    threads = [threading.Thread(target=append, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(index.ids()) == sorted(f"w{w}-{i}" for w in range(4) for i in range(15))
