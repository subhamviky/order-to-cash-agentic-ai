# 0002: The claim was settled SUCCEEDED when a BaseException escaped a step

- **Date of the work:** 2026 (found in the framework; fixed in E2A v1.8.0)
- **Severity:** SEV-3 (see the platform README)
- **Status:** Actions complete
- **Authors:** repository owner, with Claude

## Summary

E2A's `BaseWorkflow` settled the claim in a `finally` block, so a `BaseException` inside a step (for example a cancellation) completed the claim as SUCCEEDED although the step had not finished.

## Impact

None on users; the order would have been reported done without its effects.

## Timeline

- Found while reviewing the order saga's recovery against the framework.
- Fix in the framework (E2A v1.8.0): the claim is left IN_PROGRESS for recovery when a `BaseException` escapes.
- O2C picked the fix up by upgrading.

## Root cause

1. The framework treated every exit of the step as completion.
2. A test for ordinary exceptions did not cover `BaseException`.

## What went well

The framework was fixed once, for every project that uses it.

## Action items

| Action | Type | Status |
|---|---|---|
| Leave the claim IN_PROGRESS on `BaseException` | prevent | Done (E2A v1.8.0) |
