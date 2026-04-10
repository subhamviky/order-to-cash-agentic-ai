# Order-to-Cash Agentic AI Platform

> **Enterprise-grade, production-ready Agentic AI system** built on AWS — translating 13+ years of
> financial settlement architecture ($350M+ transaction volumes) into a cloud-native, AI-native platform.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.1-FF6B35?style=flat)
![AWS Bedrock](https://img.shields.io/badge/AWS_Bedrock-Claude_3-FF9900?style=flat&logo=amazonaws&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-1.6-7B42BC?style=flat&logo=terraform&logoColor=white)
![Phase 1](https://img.shields.io/badge/Phase_1-Complete-brightgreen?style=flat)
![Phase 2](https://img.shields.io/badge/Phase_2-In_Progress-blue?style=flat)

---

## Why This Project Exists

This project applies **the enterprise resilience
patterns used in production $350M financial settlement systems** — idempotency, saga compensation,
circuit breakers, exactly-once processing, DLQ escalation — directly to an AI-native architecture
running on AWS.

**Core mental model:**
```
Agent           = microservice (reasoning unit)
RAG             = CQRS knowledge retrieval layer
MCP Tool        = idempotency-aware API action
Orchestration   = saga-compensating control plane
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│             API Gateway (REST + Auth)            │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│          ALB  →  ECS Fargate (FastAPI)           │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│             LangGraph Orchestrator               │
│                                                 │
│  ┌─────────────┐                                │
│  │ RouterAgent │──► ORDER_OPS                   │
│  │  (Haiku)    │──► FINANCE    ──► RAG Retrieval│
│  └─────────────┘──► KNOWLEDGE                   │
│                          │                      │
│                 ┌─────────▼──────────┐          │
│                 │   CriticAgent      │          │
│                 │ (groundedness SLO) │          │
│                 └────────────────────┘          │
└──────────┬────────────────────┬─────────────────┘
           │                    │
┌──────────▼──────┐  ┌──────────▼──────────────┐
│   OpenSearch    │  │    SQS FIFO  +  DLQ      │
│  (RAG / KNN)    │  │   (async workflows)      │
└─────────────────┘  └──────────┬───────────────┘
                                │
                   ┌────────────▼──────────────┐
                   │   Lambda Tool Microservices│
                   │  create_order  check_stock │
                   │  risk_score    open_case   │
                   └───────────────────────────┘
```

---

## Key Engineering Decisions

| Pattern | Implementation | Enterprise Precedent |
|---------|---------------|----------------------|
| **Idempotency** | DynamoDB two-layer: GSI query + conditional expression | Same pattern as $350M settlement engine |
| **Saga Compensation** | LangGraph state machine with CriticAgent rollback | Multi-agent failure recovery |
| **Circuit Breaker** | `pybreaker` per downstream service | Bedrock, OpenSearch, tool isolation |
| **DLQ Escalation** | SQS → DLQ after 3 retries + CloudWatch alarm | Zero silent workflow drops |
| **Backoff + Jitter** | `tenacity` exponential + random jitter | Thundering herd prevention on LLM endpoints |
| **Model Routing** | RouterAgent → Haiku; specialists → Sonnet | FinOps: cost-optimised per task complexity |
| **Hybrid RAG** | BM25 + KNN → RRF → cross-encoder reranker | Higher retrieval precision than pure vector |
| **Policy-as-Code** | `governance.yaml` per-agent tool allow/deny | Approval gates, redaction, audit trails |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Server | FastAPI 0.111 + Uvicorn on ECS Fargate |
| Agent Orchestration | LangGraph — 5-agent state machine |
| LLM | Amazon Bedrock (Claude 3 Sonnet + Haiku) |
| RAG Vector Store | Amazon OpenSearch (KNN + BM25 hybrid) |
| Embeddings | sentence-transformers / Bedrock Titan |
| Tool Microservices | FastAPI + AWS Lambda (Mangum) |
| Persistence | DynamoDB (orders, cases, idempotency, LLM cache) |
| Async Queue | SQS FIFO + Dead Letter Queue |
| Infrastructure | Terraform 1.6 on AWS (ap-south-1) |
| Observability | CloudWatch + AWS X-Ray + OpenTelemetry |
| CI/CD | GitHub Actions (OIDC, no stored credentials) |
| RAG Evaluation | RAGAS (faithfulness gate in CI/CD) |

---

## Agents

| Agent | Model | Responsibility | Tools |
|-------|-------|---------------|-------|
| **RouterAgent** | Haiku | Intent classification: ORDER\_OPS / FINANCE / KNOWLEDGE | None |
| **KnowledgeAgent** | Sonnet | RAG-grounded answers with mandatory citations | OpenSearch retriever |
| **OrderOpsAgent** | Sonnet | Order creation, stock checks, validation | `create_order`, `check_stock` |
| **FinanceAgent** | Sonnet | Risk scoring, approval gates, policy enforcement | `risk_score`, `open_case` |
| **CriticAgent** | Haiku | Groundedness scoring (SLO >= 0.85), response rewriting | None |

---

## SLOs

| SLO | Target | Measured By |
|-----|--------|-------------|
| p95 Workflow Latency | < 2.5 sec | CloudWatch `WorkflowLatencyMs` p95 |
| Groundedness | >= 0.85 | RAGAS faithfulness — CI gate blocks deployment |
| Availability | >= 99.5% | ALB 5xx error rate |
| Cost per Workflow | < $0.03 | Token count x model price → `WorkflowCostUSD` |

---

## Project Status

### Phase 1 — Complete

- [x] FastAPI service on AWS Lambda
- [x] Async event processing via SQS with DLQ escalation and exponential backoff
- [x] DynamoDB two-layer idempotency (GSI query + conditional expression)
- [x] CloudWatch structured logging with correlation ID threading

### Phase 2 — In Progress

- [x] LangGraph 5-agent orchestration scaffold
- [x] All agents implemented: Router, Knowledge, OrderOps, Finance, Critic
- [x] Tool microservices: create\_order, check\_stock, risk\_score, open\_case
- [ ] Amazon Bedrock RAG pipeline (OpenSearch + RAGAS eval)
- [ ] AWS Terraform IaC (ECS Fargate, ALB, API Gateway, OpenSearch)
- [ ] GitHub Actions CI/CD with RAG eval gate and automated rollback
- [ ] NFRs: circuit breakers, FinOps model routing, policy-as-code governance

---

## Repository Structure

```
order-to-cash-agentic-ai/
├── agents/           # 5 agents (Router, Knowledge, OrderOps, Finance, Critic)
├── orchestration/    # LangGraph graph, state schema, guardrails, resilience
├── app/              # FastAPI application (routers, middleware, schemas, config)
├── rag/              # Indexer, hybrid retriever, reranker, RAGAS evaluator
├── tools/            # 4 tool microservices + Lambda handlers
├── policies/         # governance.yaml — tool allow/deny, approval gates
├── observability/    # OTel/X-Ray tracer, CloudWatch metrics, SLO checker
├── terraform/        # Full IaC: VPC, ECS, ALB, API GW, SQS, OpenSearch
├── .github/workflows/# CI/CD: test, rag-eval, policy-check, build, deploy
├── tests/            # Unit, integration, RAG evaluation tests
├── data/knowledge/   # Sample O2C knowledge corpus for RAG indexing
└── docker-compose.yml# Local dev: FastAPI + OpenSearch + tool services
```

---

## Local Development

```bash
git clone https://github.com/subhamviky/order-to-cash-agentic-ai.git
cd order-to-cash-agentic-ai
pip install poetry==1.7.1
poetry install
docker-compose up          # FastAPI + OpenSearch
poetry run pytest tests/unit/ -v
```

---

## Cloud Portability

| AWS | GCP | Purpose |
|-----|-----|---------|
| Lambda / ECS Fargate | Cloud Run | Compute |
| Amazon Bedrock | Vertex AI (Gemini) | LLM inference |
| SQS | Pub/Sub | Async queue |
| DynamoDB | Firestore / Spanner | Persistence |
| OpenSearch | Vertex AI Vector Search | RAG store |
| CloudWatch | Cloud Monitoring | Observability |

LangGraph and MCP tool patterns run identically across AWS, GCP, and Azure.

---

## Related Project

**[aws-reconciliation-engine](https://github.com/subhamviky/aws-reconciliation-engine)** —
Cloud-Native Payment Reconciliation Engine (Phase 1 live on AWS). FastAPI on Lambda, SQS async
processing, DynamoDB two-layer idempotency, CloudWatch observability. Phase 2 adds LangGraph
multi-agent + Bedrock RAG.

---

## Author

**Subham Gupta** — Staff Architect & AI Architect, SAP Labs India
13+ years delivering production distributed systems governing $350M+ in annual financial volumes.

[LinkedIn](https://www.linkedin.com/in/subham-gupta-0a05a058) · [Email](mailto:subhamviky@gmail.com)
