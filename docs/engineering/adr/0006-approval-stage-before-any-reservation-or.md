# ADR 0006: Approval stage before any reservation or charge; decided once by a finance approver who is not the requester

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Large orders need a second person's approval before money or stock moves.

## Options considered

A) Approve after reserving. B) `ApprovalStage` runs after `_prepare` and before `_act` for amounts above a threshold; `ApprovalStore.decide` is a compare-and-set on PENDING; `_authorize_decision` requires the approver role and a different person.

## Decision

B (invariants I-5, I-6).

## Consequences

Nothing is reserved or charged before approval; two approvers deciding at once: the second gets 403.
