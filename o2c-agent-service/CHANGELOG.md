# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- Trajectory cases in the release gate (hub note EV-01, E2A v1.9): four golden cases check the path a request takes (an order reserves stock before it submits the settlement, with at most two tool calls; policy and status questions call no material tool; a large order waits for approval before any tool) and two red-team cases check that an injection calls no material tool. `O2CReleaseGate._run_case` runs each on a fresh assistant; E2A's scorers score them. The domain cases keep their own scoring.
- `O2CAssistant.handle_traced()`: `handle()` and the workflow's final state.
- Online evaluation records: with `O2C_EVAL_RECORDS` set, the settled runs E2A samples (`ONLINE_EVAL_SAMPLE_RATE`) are written as redacted JSON lines. The landscape demo records every run and promotes low-scoring, fallback and refused runs into candidate cases for review (workflow artifact `o2c-online-evaluation`).

### Changed
- E2A and e2a-adapters v1.8.0 → v1.9.1.
- The router's degraded answer names its reason, UNCLASSIFIED.
