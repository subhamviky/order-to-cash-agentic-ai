# Disaster recovery: o2c-agent-service

Platform plan: [disaster recovery](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/disaster-recovery.md). Specific here: state (orders, stock, approvals, the outbox) is in Firestore; there is no export. A restart or redeploy loses nothing (claims and orders are in Firestore). Unfinished orders are recovered by the scheduled sweep with the same keys: reserved once, released once, charged once. Events not yet published remain in the outbox and go out on the next sweep. If the database is lost, orders are lost; stock is re-seeded (`create-if-absent`) and topped up; settlements already charged remain in the ledger, which is the system of record for money.

RTO for a bad revision: roll back traffic. RPO beyond Firestore's guarantees: not defined.
