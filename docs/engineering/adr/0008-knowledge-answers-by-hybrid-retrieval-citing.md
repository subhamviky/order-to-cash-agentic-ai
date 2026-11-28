# ADR 0008: Knowledge answers by hybrid retrieval, citing and grounded

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Policy questions need an answer with its sources; the spike used OpenSearch hybrid search.

## Options considered

A) A hosted index. B) BM25 plus vectors with reciprocal rank fusion re-ranked by a governed `TOP_K` (DSA), in process, over three documents; the answer must cite what it retrieved and is scored by `evaluate_answer()`; the fallback declines.

## Decision

B. Embeddings are a hashed bag of words by design (G-11); the policy index is rebuilt at start-up for the catalog's tenant (G-4).

## Consequences

Deterministic and free. A real corpus needs a hosted index and real embeddings behind the same port.
