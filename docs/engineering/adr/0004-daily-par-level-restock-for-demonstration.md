# ADR 0004: A daily par-level restock for the demonstration landscape, off by default

- **Status:** Accepted
- **Date:** 2026-11-27
- **Deciders:** repository owner

## Context

The scenario buys goods on every run; seeded stock lasts about sixteen runs.

## Options considered

A) Seed more. B) `InventoryStore.top_up` tops each SKU up to its catalog level once per UTC day, keyed `topup:<sku>:<day>`, switched by `O2C_DAILY_RESTOCK` (Terraform `daily_restock`).

## Decision

B, with `daily_restock = true` for the landscape.

## Consequences

Repeatable runs. A second restock on the same UTC day adds nothing (platform review 0008). Where stock is real, leave it off.
