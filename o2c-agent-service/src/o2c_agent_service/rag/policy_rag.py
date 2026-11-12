"""Hybrid retrieval over the O2C policies on E2A's RAG contracts.

Write side: PolicyIndexingPipeline(BaseIndexingPipeline) — ingest() is inherited; chunks
are policy paragraphs, written idempotently per chunk id into a tenant namespace.
Read side: PolicyRAGPipeline(BaseRAGPipeline) — retrieve() is inherited; the index search
fuses a keyword leg (BM25) and a vector leg (hashed bag-of-words embeddings, no model
needed) with reciprocal rank fusion, and the re-ranking keeps the best k with a governed
DSA TOP_K call. _evaluate_answer measures groundedness against what was retrieved.
"""
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

from capability_oriented_dsa import DSAFacade, SequenceState
from e2a_base import BaseIndexingPipeline, BaseRAGPipeline

POLICY_ID = re.compile(r"\bPOL-[A-Z]+-\d+\b")
WORD = re.compile(r"[a-z0-9]+")
STOP = set("a an and are as at be by can do does for from has have how i if in is it its of on or our "
           "the their this to we what when which who why will with within".split())
DIM = 256


SUFFIXES = ("iation", "ation", "ing", "ed", "es", "s")


def stem(word: str) -> str:
    """A light suffix stemmer: 'reconciled' and 'reconciliation' both become 'reconcil'."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> List[str]:
    return [stem(w) for w in WORD.findall(text.lower()) if w not in STOP]


def embed(text: str) -> List[float]:
    """Deterministic hashed bag-of-words vector (L2-normalised). The same function embeds
    documents and queries, as E2A requires (one embedding model on both sides)."""
    vector = [0.0] * DIM
    for word in tokens(text):
        vector[int(hashlib.sha1(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class PolicyIndex:
    """In-memory index, one namespace per tenant: {chunk_id: chunk}."""

    def __init__(self) -> None:
        self.namespaces: Dict[str, Dict[str, dict]] = {}

    def namespace(self, tenant_id: str) -> Dict[str, dict]:
        return self.namespaces.setdefault(f"policies_{tenant_id}", {})


class PolicyIndexingPipeline(BaseIndexingPipeline):
    def __init__(self, index: PolicyIndex) -> None:
        self.index = index

    def _chunk_documents(self, document, config=None, **kwargs):
        chunks = []
        for paragraph in document["text"].split("\n\n"):
            match = POLICY_ID.search(paragraph)
            if match:
                chunks.append({"text": paragraph.strip(),
                               "metadata": {"chunk_id": f"{document['id']}#{match.group(0)}",
                                            "doc_id": document["id"], "policy_id": match.group(0)}})
        if not chunks:
            raise ValueError(f"{document['id']}: no policy paragraphs")
        return chunks

    def _embed_documents(self, texts, config=None, **kwargs):
        return [embed(t) for t in texts]

    def _write_index(self, chunks, vectors, config=None, tenant_id=None, **kwargs):
        namespace = self.index.namespace(tenant_id)
        for chunk, vector in zip(chunks, vectors):          # upsert by chunk id: replay-safe
            meta = chunk["metadata"]
            namespace[meta["chunk_id"]] = {**meta, "text": chunk["text"], "vector": vector,
                                           "terms": Counter(tokens(chunk["text"]))}

    def _delete_from_index(self, doc_id, config=None, tenant_id=None, **kwargs):
        namespace = self.index.namespace(tenant_id)
        for chunk_id in [c for c, v in namespace.items() if v["doc_id"] == doc_id]:
            del namespace[chunk_id]

    def _handle_error(self, error, document, config=None, **kwargs):
        kwargs.get("failed_keys", []).append(document.get("id"))


def load_knowledge(folder: Path) -> List[dict]:
    return [{"id": p.name, "op": "upsert", "text": p.read_text(encoding="utf-8")}
            for p in sorted(Path(folder).glob("*.md"))]


class PolicyRAGPipeline(BaseRAGPipeline):
    RRF_K = 60

    def __init__(self, index: PolicyIndex) -> None:
        self.index = index
        self.dsa = DSAFacade()

    def _search_index(self, query_text, query_vector, config=None, tenant_id=None, **kwargs):
        chunks = list(self.index.namespace(tenant_id).values())
        query_terms = tokens(query_text)
        if not chunks or not query_terms:
            return []
        # keyword leg: BM25
        n, avg = len(chunks), sum(sum(c["terms"].values()) for c in chunks) / len(chunks)
        df = Counter(t for c in chunks for t in set(c["terms"]))
        def bm25(c):
            length, score = sum(c["terms"].values()), 0.0
            for t in query_terms:
                f = c["terms"].get(t, 0)
                if f:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / avg))
            return score
        # vector leg: the base passes a provider placeholder, so the query is embedded here
        # with the same function the indexing pipeline used for the documents
        qv = embed(query_text)
        keyword = {c["chunk_id"]: bm25(c) for c in chunks}
        vector = {c["chunk_id"]: sum(a * b for a, b in zip(qv, c["vector"])) for c in chunks}
        candidates = [c for c in chunks if keyword[c["chunk_id"]] > 0]   # no shared term, no evidence
        rank_k = {cid: r for r, cid in enumerate(sorted(keyword, key=lambda c: -keyword[c]), 1)}
        rank_v = {cid: r for r, cid in enumerate(sorted(vector, key=lambda c: -vector[c]), 1)}
        return [{"chunk_id": c["chunk_id"], "policy_id": c["policy_id"], "text": c["text"],
                 "score": 1 / (self.RRF_K + rank_k[c["chunk_id"]]) + 1 / (self.RRF_K + rank_v[c["chunk_id"]]),
                 "keyword": round(keyword[c["chunk_id"]], 3), "vector": round(vector[c["chunk_id"]], 3)}
                for c in candidates]

    def _rerank(self, results, config=None, **kwargs):
        if not results:
            return []
        k = int(kwargs.get("rerank_top_n", 3))
        by_id = {r["chunk_id"]: r for r in results}
        top = self.dsa.execute(structure_type="SEQUENCE", capability="QUERY", operation="TOP_K",
                               state=SequenceState([(r["score"], r["chunk_id"]) for r in results]),
                               k=k, largest=True).data
        return [by_id[chunk_id] for _, chunk_id in sorted(top, reverse=True)]

    def _evaluate_answer(self, answer, config=None, **kwargs) -> float:
        """Groundedness: share of the answer's sentences that cite a retrieved policy and
        whose content words appear in that policy's text. No citation, no credit."""
        retrieved = {r["policy_id"]: set(tokens(r["text"])) for r in kwargs.get("retrieved", [])}
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", (answer or "").strip()) if s]
        if not sentences:
            return 0.0
        grounded = 0
        for sentence in sentences:
            cited = [p for p in POLICY_ID.findall(sentence) if p in retrieved]
            words = set(tokens(POLICY_ID.sub("", sentence)))
            if cited and words and len(words & set().union(*(retrieved[p] for p in cited))) / len(words) >= 0.6:
                grounded += 1
        return grounded / len(sentences)
