# ADR 0003: Stock is a compare-and-set counter; a keyed change records its key in the same write

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Two orders racing for the last unit, or a retried reserve, must never oversell or reserve twice.

## Options considered

A) A lock. B) `InventoryStore` compare-and-set loops; a keyed change records its key in the same write and is not repeated.

## Decision

B (invariant I-3).

## Consequences

Safe with several instances on one Firestore database. Stock is finite: after about sixteen scenario runs it is used up (platform review 0002).
