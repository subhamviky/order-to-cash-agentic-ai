# Post-incident reviews

Blameless reviews of failures found while building and operating this service. None affected a user (the landscape is synthetic); each cost real time or showed a design gap. Severity scale and conventions: see the [platform README](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/postmortems/README.md). Template: [`TEMPLATE.md`](TEMPLATE.md).

## Reviews specific to this repository

| # | Review | Severity |
|---|---|---|
| [0001](0001-crash-inside-order-saga-stranded-stock-or.md) | A crash inside the order saga stranded stock or an order | SEV-3 |
| [0002](0002-claim-was-settled-succeeded-when-baseexception.md) | The claim was settled SUCCEEDED when a BaseException escaped a step | SEV-3 |

## Platform reviews that touched this repository

- [O2C stock exhausted, scenario step 1 failing](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/postmortems/0002-o2c-stock-exhausted.md)
- [The promotion pipeline's first runs failed (same-day restock)](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/postmortems/0008-promotion-pipeline-first-runs-failed.md)
- [A seeded ledger account drained by the test payment](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/postmortems/0001-ledger-account-drained-by-test-payment.md)
