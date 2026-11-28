# ADR 0011: Admission control at 20 requests in flight

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

A burst must not exhaust the service.

## Options considered

A) Unbounded. B) E2A's capacity stage: more than 20 in flight gives `CapacityRefusal` and HTTP 503.

## Decision

B.

## Consequences

Overload sheds load with a retryable error.
