# ADR 0005: A transactional outbox of order events, published by a leased sweeper, de-duplicated by consumers

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Order state changes must be announced to Pub/Sub exactly in step with the order.

## Options considered

A) Publish after the commit. B) `put_if_version(..., outbox=[event])` commits order and event together; `POST /internal/events/publish` (or the scheduler) publishes under a lease; consumers de-duplicate on `order_id:status`.

## Decision

B (invariant I-7). A second concurrent sweep returns SKIPPED_LOCKED.

## Consequences

At-least-once events with no lost change. The subscription has no consumer in the landscape (G-7).
