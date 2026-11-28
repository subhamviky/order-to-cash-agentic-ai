# Release process: o2c-agent-service

Platform workflows: [release process](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/release-process.md). For this repository:

1. Branch and pull request. CI (`o2c-ci`): tests with settlement-service and reconciliation-service replaced by in-process fakes; the tests again with state in the Firestore emulator and events to the Pub/Sub emulator, several instances on one database; the AI-DLC release gate (E2A `ProjectReleaseGate`, seven stages); Terraform fmt, validate, test with a mock provider; the container image is built and run, and asked a policy question.
2. Merge to `main`. A release is a commit and a Cloud Run revision (the service is `o2c-agent-service-dev`).
3. Deploy: Actions, `ops` (assistant repository), `deploy`, service `o2c-agent-service-dev`. No canary. A new revision starts and, with `O2C_DAILY_RESTOCK=true`, tops stock up on its first start once per UTC day.
4. Verify: `landscape-gcp` on `main`.
5. Rollback: `gcloud run services update-traffic o2c-agent-service-dev --region us-central1 --to-revisions <previous>=100`. Keyed effects make a rolled-back revision safe to resume.

`landscape-demo.yml` runs the cross-landscape demo; `aidlc-change.yml` and `aidlc-scaffold.yml` are the AI-DLC pipelines that scaffolded and changed the project.
