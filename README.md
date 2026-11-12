# Order-to-Cash Agentic AI Platform

> `main` is built by **consuming** the E2A framework family: the AI-DLC pipeline scaffolds the
> service (P0 + G2C + A2C), five E2A agents run in one E2A workflow, every material action goes
> through governed tools with typed outcomes, and an AI-DLC release gate decides what ships.

| Service | Stack | Role |
|---|---|---|
| `o2c-agent-service` | Python 3.12, FastAPI, E2A, DSA; Cloud Run (Terraform) | Natural-language front door: orders with human approval, payment status, payment exceptions, policy answers; MCP tools |

It calls the two systems of record of the landscape:
[financial-settlement-platform](https://github.com/subhamviky/financial-settlement-platform) (money) and
[aws-reconciliation-engine](https://github.com/subhamviky/aws-reconciliation-engine) (cash matching).
CI: `o2c-ci`. The whole landscape runs together in `landscape-demo`.
Requirements and the step-by-step guide live in the private hub (`o2c/`).

## Branches and tags

| Branch / tag | Purpose |
|---|---|
| `main` | Framework-consumption build. |
| `spike/v1-original` · tag `spike-v1` | Snapshot of the original spike (LangGraph, Bedrock, AWS). Frozen. |
| `aidlc/o2c-agent-service` | The untouched AI-DLC scaffold, as generated. |

## Framework family

[E2A](https://github.com/subhamviky/e2a-framework) ·
[A2C · G2C · P0](https://github.com/subhamviky/a2c-framework) ·
[Capability-Oriented DSA](https://github.com/subhamviky/capability-oriented-dsa)
