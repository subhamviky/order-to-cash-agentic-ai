# Capacity: o2c-agent-service

Platform note: [capacity](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/capacity.md). Resources: Cloud Run `o2c-agent-service-dev` (scale to zero; up to three instances were tested; 20 requests in flight), Firestore collections, a Pub/Sub topic for order events with a subscription nobody consumes, a combined Cloud Scheduler job (events and order recovery), service accounts.

What breaks first: seeded stock (50 printers and 200 scanners; tops up once per UTC day); the 20-in-flight admission limit; the model's rate limits when a managed provider is selected (the default is simulated). The policy index and the embeddings are in process, fine for three documents.
