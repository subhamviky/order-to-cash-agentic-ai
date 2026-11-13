"""An append-only list of ids kept in fixed-size pages on an E2A BaseTransactionalStore.

One growing document would hit the store's document limit (about 22,000 ids in Firestore's
900 KB value), after which every new approval would fail to save. Pages
of ``page_size`` ids each, plus a head row with the page count, keep every document small.
Appends are compare-and-set: concurrent instances never lose an id. An id appended twice
around a page roll-over is read back once.
"""
from typing import Iterator, List

from e2a import BaseTransactionalStore


class PagedIndex:
    def __init__(self, rows: BaseTransactionalStore, name: str, page_size: int = 500) -> None:
        self.rows, self.name, self.page_size = rows, name, page_size

    def _head(self):
        return self.rows.get_versioned(f"{self.name}:head") or ({"pages": 1}, None)

    def append(self, item_id: str) -> None:
        while True:
            head, head_version = self._head()
            page_key = f"{self.name}:page:{head['pages'] - 1}"
            page, page_version = self.rows.get_versioned(page_key) or ({"ids": []}, None)
            if item_id in page["ids"]:
                return
            if len(page["ids"]) < self.page_size:
                if self.rows.put_if_version(page_key, {"ids": page["ids"] + [item_id]}, page_version).committed:
                    return
                continue                                   # another replica appended first: read again
            # The last page is full: open the next one (one replica wins; the others read again).
            self.rows.put_if_version(f"{self.name}:head", {"pages": head["pages"] + 1}, head_version)

    def __iter__(self) -> Iterator[str]:
        seen = set()
        for number in range(self._head()[0]["pages"]):
            for item_id in (self.rows.get(f"{self.name}:page:{number}") or {"ids": []})["ids"]:
                if item_id not in seen:
                    seen.add(item_id)
                    yield item_id

    def ids(self) -> List[str]:
        return list(self)
