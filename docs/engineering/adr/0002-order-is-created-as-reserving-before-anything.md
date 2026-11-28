# ADR 0002: An order is created as RESERVING before anything moves, with keyed stock and charge changes

- **Status:** Accepted
- **Date:** 2026 (order recovery)
- **Deciders:** repository owner

## Context

A crash inside the order saga left stock reserved with no order, or an order in PENDING_PAYMENT after the money moved; a `409` from settlement-service was taken as a decline (gap G-3).

## Options considered

A) Record the order at the end. B) Record the order RESERVING first, key every stock change (`ORD-…:release`) and the charge (`Idempotency-Key` = order id), share `advance_order` between the request and recovery, treat `409` as UNKNOWN.

## Decision

B (invariants I-2, I-3, I-4).

## Consequences

An unfinished order can be finished with the same keys: reserved once, released once, charged once. A crash after the claim but before the order is recorded leaves nothing to recover (G-12, minor).
