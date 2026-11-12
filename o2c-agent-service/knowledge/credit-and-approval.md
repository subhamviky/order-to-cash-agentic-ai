# Credit and approval

POL-CREDIT-01 Credit limit. An order is accepted only if its amount does not exceed the customer's credit limit. An order above the credit limit is refused and no stock is reserved.

POL-CREDIT-02 Customers on hold. A customer whose payer account is blocked cannot place orders; the settlement is rejected and the reservation is released.

POL-APPROVAL-01 Large orders. Orders above 5,000.00 EUR wait for approval by a finance approver before any stock is reserved or money moves. The person who requested the order can never approve it (four-eyes principle).
