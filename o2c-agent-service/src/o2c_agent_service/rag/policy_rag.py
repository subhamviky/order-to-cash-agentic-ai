"""Hybrid retrieval over the O2C policies on E2A's RAG contracts (v1.2: shared ports).

The two sides share two ports, so they cannot drift (E2A design note 01, option C):
  HashedBagOfWords (BaseEmbeddingModel)  one deterministic embedding for documents and queries
  PolicyIndex      (BaseVectorIndex)     one namespace per tenant; search() fuses a keyword
                                         leg (BM25) and a vector leg with reciprocal rank fusion
Write side: PolicyIndexingPipeline(BaseIndexingPipeline) supplies only the chunking.
Read side: PolicyRAGPipeline(BaseRAGPipeline) supplies the re-ranking (a governed DSA TOP_K
call) and the groundedness check, which callers reach through the public evaluate_answer().
policy_rag() composes both into E2A's RAGPipeline facade.
"""
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

from capability_oriented_dsa import DSAFacade, SequenceState
from e2a import BaseEmbeddingModel, BaseIndexingPipeline, BaseRAGPipeline, BaseVectorIndex, RAGPipeline

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


class HashedBagOfWords(BaseEmbeddingModel):
    model_id = f"hashed-bow-{DIM}"

    def embed_documents(self, texts):
        return [embed(t) for t in texts]

    def embed_query(self, text):
        return embed(text)


class PolicyIndex(BaseVectorIndex):
    """In-memory index, one namespace per tenant: {chunk_id: chunk}. Upsert by chunk id,
    so a replayed ingest is safe."""
    RRF_K = 60

    def __init__(self) -> None:
        self.namespaces: Dict[str, Dict[str, dict]] = {}

    def upsert(self, namespace, chunks, vectors):
        space = self.namespaces.setdefault(namespace, {})
        for chunk, vector in zip(chunks, vectors):
            meta = chunk["metadata"]
            space[meta["chunk_id"]] = {**meta, "text": chunk["text"], "vector": vector,
                                       "terms": Counter(tokens(chunk["text"]))}

    def delete(self, namespace, doc_id):
        space = self.namespaces.get(namespace, {})
        for chunk_id in [c for c, v in space.items() if v["doc_id"] == doc_id]:
            del space[chunk_id]

    def search(self, namespace, query_text, query_vector, top_k):
        chunks = list(self.namespaces.get(namespace, {}).values())
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
        # vector leg: the query vector comes from the same embedding model as the documents
        keyword = {c["chunk_id"]: bm25(c) for c in chunks}
        vector = {c["chunk_id"]: sum(a * b for a, b in zip(query_vector, c["vector"])) for c in chunks}
        candidates = [c for c in chunks if keyword[c["chunk_id"]] > 0]   # no shared term, no evidence
        rank_k = {cid: r for r, cid in enumerate(sorted(keyword, key=lambda c: -keyword[c]), 1)}
        rank_v = {cid: r for r, cid in enumerate(sorted(vector, key=lambda c: -vector[c]), 1)}
        hits = [{"chunk_id": c["chunk_id"], "policy_id": c["policy_id"], "text": c["text"],
                 "score": 1 / (self.RRF_K + rank_k[c["chunk_id"]]) + 1 / (self.RRF_K + rank_v[c["chunk_id"]]),
                 "keyword": round(keyword[c["chunk_id"]], 3), "vector": round(vector[c["chunk_id"]], 3)}
                for c in candidates]
        return sorted(hits, key=lambda h: -h["score"])[:top_k]


class PolicyIndexingPipeline(BaseIndexingPipeline):
    namespace_prefix = "policies"

    def __init__(self, model: BaseEmbeddingModel, index: BaseVectorIndex) -> None:
        self.embedding_model, self.vector_index = model, index

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

    def _handle_error(self, error, document, config=None, **kwargs):
        pass                                # the base already lists the document in failed_keys


def load_knowledge(folder: Path) -> List[dict]:
    return [{"id": p.name, "op": "upsert", "text": p.read_text(encoding="utf-8")}
            for p in sorted(Path(folder).glob("*.md"))]


class PolicyRAGPipeline(BaseRAGPipeline):
    namespace_prefix = "policies"

    def __init__(self, model: BaseEmbeddingModel, index: BaseVectorIndex) -> None:
        self.embedding_model, self.vector_index = model, index
        self.dsa = DSAFacade()

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


def policy_rag() -> RAGPipeline:
    """Both sides over one embedding model and one index (refused if the models differ)."""
    model, index = HashedBagOfWords(), PolicyIndex()
    return RAGPipeline(PolicyIndexingPipeline(model, index), PolicyRAGPipeline(model, index))
