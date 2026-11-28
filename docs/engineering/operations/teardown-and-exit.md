# Teardown: o2c-agent-service

Platform order and verification: [teardown](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/teardown-and-exit.md). From this repository: export the last scenario summary; `terraform destroy` in `o2c-agent-service/infra` (Cloud Run, topic and subscription, scheduler job, service accounts, Firestore collections); delete the repository variables.
