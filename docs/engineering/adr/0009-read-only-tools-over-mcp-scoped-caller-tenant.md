# ADR 0009: Read-only tools over MCP, scoped to the caller's tenant

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

Other agents may need stock and order status without write access.

## Options considered

A) No external access. B) `POST /mcp` (JSON-RPC 2.0) exposes `check_stock` and `get_order` only, adding the caller's tenant.

## Decision

B (invariant I-8).

## Consequences

Read-only external use with the same tenant filter as the API.
