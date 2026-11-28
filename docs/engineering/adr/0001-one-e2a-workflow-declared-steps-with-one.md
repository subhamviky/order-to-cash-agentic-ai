# ADR 0001: One E2A workflow of declared steps with one idempotency claim, replacing the spike's LangGraph state machine

- **Status:** Accepted
- **Date:** 2026 (completed project)
- **Deciders:** repository owner

## Context

The spike used a LangGraph state machine with five agents on Bedrock and OpenSearch. Controls (idempotency, approval, recovery) were re-implemented in each node.

## Options considered

A) Keep LangGraph. B) One `O2CWorkflow` on E2A (`Steps`, `Step`, `Route`, `resume()`): route, intake, then the specialist (execution, finance, knowledge) under one claim; an approval resumes the order at its paused step.

## Decision

B. The router and agents are generated skeletons completed by hand; every model output is checked before use.

## Consequences

One place for claim, approval and recovery. The model boundary is E2A's `SimulatedLLMService` by default (a managed provider by profile).
