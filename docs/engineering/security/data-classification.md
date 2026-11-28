# Data classification: o2c-agent-service

All data is synthetic ([platform rule](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/security/data-classification.md)). If it were real:

| Data | Where | Classification | Retention here | Protection |
|---|---|---|---|---|
| Orders (customer, SKU, quantity, amount, status, settlement id) | Firestore (collection prefix `o2c`) | Confidential | until teardown | private service; tenant filter on every store |
| Stock levels and keyed changes | Firestore | Internal | until teardown | compare-and-set |
| Approvals | Firestore | Confidential | until teardown | decided once by a different approver |
| Order events (outbox, Pub/Sub) | Firestore, Pub/Sub topic | Confidential | until published | tenant on every event |
| Catalog and policy documents | files in the image | Internal | with the image | read-only |
| Model calls and usage (`/api/v1/usage`) | in memory | Internal | process lifetime | |
| Logs | Cloud Logging | Internal | default | ids and statuses |

Handling: no real data; the model (simulated by default) sees order facts only because they are synthetic.
