# Requirements and user stories

Use cases (UC-1 to UC-7) and requirements are traced in the design document, section 2. Stories with acceptance criteria that are tests:

| # | As a... | I want... | So that... | Acceptance |
|---|---|---|---|---|
| O1 | salesperson | to place an order in plain language | I do not fill in a form | the order is parsed, validated against the catalog, priced, and paid through settlement, or refused with a reason |
| O2 | salesperson | the same order sent twice to be one order | a retry does not double-charge | same key and content replays; a different order with the same key conflicts |
| O3 | finance approver | large orders to wait for my approval, decided by someone other than the requester | no one approves their own order | nothing is reserved or charged before approval; a different approver; decided once |
| O4 | salesperson | a declined payment to release the stock | stock is not stranded | the order is CANCELLED and the stock released once |
| O5 | operator | unfinished orders to finish themselves | no order stays half-done | the five-minute sweep finishes or removes them with the same keys |
| O6 | finance analyst | to ask about an order's payment and exceptions | I see the facts | facts are read first; any id, amount or status not in them is refused |
| O7 | employee | answers to policy questions with sources | I can check them | the answer cites what it retrieved or declines |
| O8 | another agent | read-only stock and order tools | I can use O2C safely | `/mcp` exposes `check_stock` and `get_order` for the caller's tenant only |
| O9 | operator | the demonstration landscape to keep stock | repeated scenario runs keep working | `O2C_DAILY_RESTOCK` tops up once a day |

Non-functional: private by default; admission control at 20 in flight. Out of scope: real inventory systems, real payments, a user interface.
