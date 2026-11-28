# Changelog

Newest first. [Keep a Changelog](https://keepachangelog.com). Released by commit and Cloud Run revision.

## 28 November 2026
### Added
- Engineering records (`docs/engineering/`).

## 27 November 2026 (GCP-02 Phase B)
### Added
- Correlation id forwarded on calls to settlement and reconciliation.
- `InventoryStore.top_up` and `O2C_DAILY_RESTOCK`: a daily par-level restock for the demonstration landscape, on in the Terraform stack (`daily_restock = true`).

## 25 November 2026 (GCP-01)
### Added
- Google Cloud deployment: Firestore state, Pub/Sub order events, Cloud Scheduler sweep, identity at ingress.

## Earlier
- Order recovery (keyed effects, RESERVING first, scheduled sweep); the completed project rebuilt from the spike on the E2A and A2C frameworks.
