# Cost and capacity: o2c-agent-service

Free tier ([platform note](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/cost-and-capacity.md)). Resources: Cloud Run `o2c-agent-service-dev` (scale to zero, up to three instances were tested, 20 requests in flight), Firestore collections, a Pub/Sub topic for order events with a subscription nobody consumes, a combined Cloud Scheduler job (events and order recovery; one of the three free jobs), service accounts.

What breaks first: seeded stock (50 printers and 200 scanners); the 20-in-flight admission limit; the model's quota when a managed provider is selected (the default is simulated). The policy index and the embeddings are in process, fine for three documents.
