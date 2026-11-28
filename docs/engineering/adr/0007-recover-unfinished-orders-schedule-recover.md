# ADR 0007: Recover unfinished orders on a schedule (`recover_stuck`, every five minutes), never taking over a live claim

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Unfinished orders were recovered only on request (G-2).

## Options considered

A) Manual `POST …/recover` only. B) A scheduled sweep: orders open longer than `O2C_RECOVERY_AFTER_SECONDS` (600, past the request's lease) go through `O2CRecovery`; final or missing entries are removed.

## Decision

B (`POST /internal/orders/recover`, one of the account's three Cloud Scheduler jobs, combined with the event sweep).

## Consequences

No order stays half-done unnoticed. The three scheduler jobs of the account are all in use.
