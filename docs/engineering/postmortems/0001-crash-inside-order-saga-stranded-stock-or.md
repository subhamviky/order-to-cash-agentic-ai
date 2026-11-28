# 0001: A crash inside the order saga stranded stock or an order

- **Date of the work:** 2026 (recorded in the design as gap G-3; the day was not recorded)
- **Severity:** SEV-3 (see the platform README)
- **Status:** Actions partly open
- **Authors:** repository owner, with Claude

## Summary

A crash between steps of the order saga could leave stock reserved with no order (lost), or an order in PENDING_PAYMENT after the money moved; and a `409` from settlement-service (the key still in progress there) was taken as a decline, which could release stock after a charge.

## Impact

None on users: the design records it as a gap that was fixed with tests. How it was found was not recorded.

## Timeline

- The design's gap G-3 records two orderings of the saga that recovery could not finish.
- Fix: the order is recorded RESERVING first; stock changes and the charge are keyed; `advance_order` is shared by the request and recovery; recovery takes RESERVING and PENDING_PAYMENT; `409` is UNKNOWN and parks the claim as RECOVERY_REQUIRED naming the order.
- `test_order_recovery.py` runs on memory and on the emulators.

## Root cause

1. The saga recorded the order late, after effects that were hard to undo.
2. The retry path and the recovery path were separate code that disagreed.

## What went well

Every effect is keyed, so recovery is safe to repeat.

## Action items

| Action | Type | Status |
|---|---|---|
| Record first, key every effect, one `advance_order` | prevent | Done |
| A recovery path for a claim with no order (G-12) | prevent | Open (minor: nothing moved) |
