# ADR 0010: Cloud Run IAM with a Google ID token; service-to-service tokens exchanged where needed

- **Status:** Accepted
- **Date:** 2026-11 (SI-01, GCP-01)
- **Deciders:** repository owner

## Context

Calls to settlement-service and reconciliation-service carried `X-Tenant-Id` only (G-1).

## Options considered

A) Header trust. B) Verified caller identity at ingress; outbound calls attach this service's own token; the exception query uses reconciliation's `/service/v1` route.

## Decision

B. `/internal/*` and `/api/v1/usage` have no caller check in the service (G-8): only direct Cloud Run invokers reach them.

## Consequences

No secret to leak. A role check on the internal routes would make the protection explicit.
