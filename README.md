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
| LangGraph state machine with five agents | One E2A workflow of declared steps: router (G2C-generated skeleton) → intake → the specialist (execution, finance, knowledge), under one idempotency claim; an approval resumes the order at its paused step | E2A `BaseWorkflow` (`Steps`, `resume`), `BaseAgent` |
| Bedrock models | E2A `SimulatedLLMService` behind the same boundary; every model output is checked before use | E2A LLM service boundary |
| OpenSearch hybrid search | BM25 + vectors with reciprocal rank fusion, re-ranked by a governed `TOP_K`; answers must cite and be grounded; one embedding model and one index shared by both sides | E2A `RAGPipeline` (embedding and index ports); DSA `TOP_K` |
| `governance.yaml` tool matrix | Kept and extended: entitlements, tool allow-list, approval threshold with four eyes, firewall, PII redaction, capacity, as ordered governance stages with typed refusals | E2A `BaseGovernanceFramework` (stages), `BaseValidationService` |
| Lambda tool microservices | Governed tools with typed outcomes calling the **real** settlement and reconciliation services, reads through `io_read` and payments through `io_modify`; an unknown outcome is recovered with the same idempotency key, never charged twice | E2A `BaseToolService`, `BaseMCPServer`, `BaseReconciliationService` |
| AWS deployment | Google Cloud, as Terraform only; container image built and smoke-tested in CI; an AI-DLC release gate (seven stages, RAGAS gate, red team) decides what ships | A2C GCP landing zone; E2A `BasePipeline` |

## Google Cloud (free tier) — hub design note GCP-01

O2C has always run on Google Cloud. For the free tier, `o2c-agent-service/infra` takes variables; their defaults keep the full setup.

| | Full setup (defaults) | Free tier ([`deploy/gcp/binding.vars`](deploy/gcp/binding.vars)) |
|---|---|---|
| State | its own Firestore database, PITR, delete protection | the project's one free database, `(default)`, shared by the landscape; O2C's documents in collection `o2c` |
| Images | its own Artifact Registry repository | the landscape's one repository |
| Schedules | two Cloud Scheduler jobs (events every minute, recovery every five) | one job calling `POST /internal/jobs/scheduled`, which does both (the landscape has three free jobs) |
| Who calls | API Gateway verifies an Identity Platform token (`gcp_api_gateway`) | Cloud Run IAM verifies the caller's Google ID token (`gcp_cloud_run`, E2A v1.11.0); the deployment grants each caller its tenants and roles (`identity_subject_roles`) |
| Calls to settlement and reconciliation | Google ID token exchanged for an Entra token | the Google ID token itself (`workload_identity = "gcp_id_token"`), checked by the targets' Cloud Run IAM |
| Model | E2A's simulated model | simulated, or Gemini through the Gemini Developer API's free tier (`llm_profile = "gemini_api"`; the image built with `--build-arg POETRY_EXTRAS=gemini`, the key in Secret Manager) |
| Instances | up to 3 | 1 |

The model is chosen by `E2A_PROVIDER_PROFILE` (`build_o2c_llm()`); the agents and their output checks do not change. `infra/tests/gcp.tftest.hcl` plans the free-tier variant against a mock provider.

## The project

| Service | Stack | Role |
|---|---|---|
| `o2c-agent-service` | Python 3.12, FastAPI, E2A, DSA; Cloud Run (Terraform) | Orders with human approval, payment status, payment exceptions, policy answers; MCP tools |

**Its place in the landscape:** places orders as settlements in [financial-settlement-platform](https://github.com/subhamviky/financial-settlement-platform) and reads open exceptions from [payment-reconciliation-engine](https://github.com/subhamviky/payment-reconciliation-engine). The `landscape-demo` workflow runs all three projects together in sixteen checked steps, from an order in plain language to a write-off in the settlement ledger.

## Design

The full design (HLD and LLD) of `o2c-agent-service` is in [`docs/design/`](docs/design/README.md): [Markdown](docs/design/O2C_DESIGN.md) with diagrams, and a [PDF copy](docs/design/O2C_Design_Document.pdf).

## Evidence

Verified in CI (`o2c-ci`) on every push: the test suite, the AI-DLC release gate, Terraform `fmt`/`validate`/`test`, and the container image. `landscape-demo` runs the three projects together on demand. This is an architecture reference implementation: no real model, no deployment, no production claims.

## Branches and tags

| Branch / tag | Purpose |
|---|---|
| `main` | The completed project, built on the framework family. |
| `spike/v1-original` · tag `spike-v1` | The architectural spike, frozen. `spike-v1` is the untouched snapshot. |
| `aidlc/o2c-agent-service` | The scaffold exactly as the AI-DLC pipeline generated it. |
