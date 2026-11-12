# Order-to-Cash Agentic AI Platform

> The natural-language front door of the Order-to-Cash landscape. Sales, finance and approvers
> talk to one assistant; agents understand the request, but every material action runs through
> governed tools with typed outcomes against the two systems of record.

## From spike to frameworks to project

This repository went through three stages. Each one is kept, so the path can be followed.

| Stage | Where | What happened |
|---|---|---|
| **1. Architectural spike** | branch [`spike/v1-original`](https://github.com/subhamviky/order-to-cash-agentic-ai/tree/spike/v1-original) (tag `spike-v1`) | A multi-agent design (router, specialists, critic) on LangGraph, Bedrock and OpenSearch, with policy-as-code for tools. It mapped the enterprise mental model onto agents (agent = microservice, RAG = query side, tool = idempotent action) and showed what that mapping needs: contracts every agent inherits, not conventions each one re-implements. |
| **2. Frameworks** | [E2A](https://github.com/subhamviky/e2a-framework) · [A2C · G2C · P0](https://github.com/subhamviky/a2c-framework) · [Capability-Oriented DSA](https://github.com/subhamviky/capability-oriented-dsa) | Those contracts became E2A (`BaseAgent`, `BaseWorkflow`, RAG, tools, MCP, governance, validation, release pipeline); generation became G2C, P0 and A2C; delivery became the AI-DLC pipeline and its release gates. |
| **3. Completed project** | **`main`** (this branch) | The spike rebuilt by **consuming** those frameworks, and connected to the other two projects as real systems of record. |

### What changed between the spike and `main`

| In the spike | In `main` | Framework that made the difference |
|---|---|---|
| LangGraph state machine with five agents | One E2A workflow with an agent registry: router (G2C-generated skeleton), intake, execution, finance, knowledge | E2A `BaseWorkflow`, `BaseAgent` |
| Bedrock models | E2A `SimulatedLLMService` behind the same boundary; every model output is checked before use | E2A LLM service boundary |
| OpenSearch hybrid search | BM25 + vectors with reciprocal rank fusion, re-ranked by a governed `TOP_K`; answers must cite and be grounded | E2A `BaseRAGPipeline`, `BaseIndexingPipeline`; DSA `TOP_K` |
| `governance.yaml` tool matrix | Kept and extended: entitlements, tool allow-list, approval threshold with four eyes, firewall, PII redaction, capacity | E2A `BaseGovernanceFramework`, `BaseValidationService` |
| Lambda tool microservices | Governed tools with typed outcomes calling the **real** settlement and reconciliation services; an unknown outcome is recovered with the same idempotency key, never charged twice | E2A `BaseToolService`, `BaseMCPServer` |
| AWS deployment | Google Cloud, as Terraform only; container image built and smoke-tested in CI; an AI-DLC release gate (seven stages, RAGAS gate, red team) decides what ships | A2C GCP landing zone; E2A `BasePipeline` |

## The project

| Service | Stack | Role |
|---|---|---|
| `o2c-agent-service` | Python 3.12, FastAPI, E2A, DSA; Cloud Run (Terraform) | Orders with human approval, payment status, payment exceptions, policy answers; MCP tools |

**Its place in the landscape:** places orders as settlements in [financial-settlement-platform](https://github.com/subhamviky/financial-settlement-platform) and reads open exceptions from [aws-reconciliation-engine](https://github.com/subhamviky/aws-reconciliation-engine). The `landscape-demo` workflow runs all three projects together in sixteen checked steps, from an order in plain language to a write-off in the settlement ledger.

## Evidence

Verified in CI (`o2c-ci`) on every push: the test suite, the AI-DLC release gate, Terraform `fmt`/`validate`/`test`, and the container image. `landscape-demo` runs the three projects together on demand. This is an architecture reference implementation: no real model, no deployment, no production claims.

## Branches and tags

| Branch / tag | Purpose |
|---|---|
| `main` | The completed project, built on the framework family. |
| `spike/v1-original` · tag `spike-v1` | The architectural spike, frozen. `spike-v1` is the untouched snapshot. |
| `aidlc/o2c-agent-service` | The scaffold exactly as the AI-DLC pipeline generated it. |
