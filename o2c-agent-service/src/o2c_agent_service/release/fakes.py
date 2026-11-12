"""In-process stand-ins for settlement-service and reconciliation-service, speaking their
real HTTP contracts through httpx.MockTransport. Used by the tests and by the release
gate; the cross-landscape demo runs the real services instead."""
import asyncio
import json
import uuid
from decimal import Decimal
from typing import Dict, List

import httpx


class FakeSettlementService:
    """POST /api/v1/settlements (Idempotency-Key) and GET /api/v1/settlements/{id}."""

    def __init__(self) -> None:
        self.balances = {"ACC-1000": Decimal("1000000.00"), "ACC-2000": Decimal("50000.00"),
                         "ACC-3000": Decimal("0.00"), "ACC-BLOCKED": Decimal("10000.00")}
        self.blocked = {"ACC-BLOCKED"}
        self.by_key: Dict[str, tuple] = {}
        self.by_id: Dict[str, dict] = {}
        self.posts = 0
        self.fail_next = 0             # answer 503 before committing anything
        self.answer_delay = 0.0        # commit, then answer late (every answer, replays too)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            view = self.by_id.get(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=view) if view else httpx.Response(404, json={"error": "not found"})
        self.posts += 1
        if self.fail_next:
            self.fail_next -= 1
            return httpx.Response(503, json={"error": "unavailable"})
        key = request.headers.get("Idempotency-Key")
        replayed = key in self.by_key
        if not replayed:
            status, view = self._execute(json.loads(request.content))
            self.by_key[key] = (status, view)
            self.by_id[view["settlementId"]] = view
        status, view = self.by_key[key]
        if self.answer_delay:
            await asyncio.sleep(self.answer_delay)
        return httpx.Response(status, json=view, headers={"Idempotent-Replayed": str(replayed).lower()})

    def _execute(self, cmd: dict) -> tuple:
        amount = Decimal(cmd["amount"])
        view = {"settlementId": str(uuid.uuid4()), "payerAccount": cmd["payerAccount"],
                "payeeAccount": cmd["payeeAccount"], "amount": float(amount), "currency": cmd["currency"]}
        if cmd["payerAccount"] in self.blocked:
            return 422, {**view, "status": "REJECTED", "reason": "account blocked by policy"}
        if self.balances[cmd["payerAccount"]] < amount:
            return 422, {**view, "status": "REJECTED", "reason": "insufficient funds"}
        if amount > Decimal("250000.00"):
            return 201, {**view, "status": "COMPENSATED", "reason": "clearing declined"}
        self.balances[cmd["payerAccount"]] -= amount
        self.balances[cmd["payeeAccount"]] += amount
        return 201, {**view, "status": "COMPLETED", "reason": None}


class FakeReconciliationService:
    """GET /api/v1/exceptions?status=OPEN in reconciliation-service's response format."""

    def __init__(self) -> None:
        self.cases: List[dict] = []
        self.down = False

    def add_case(self, line_id: str, kind: str, detail: str, action: str) -> None:
        self.cases.append({"line_id": line_id, "kind": kind, "detail": detail, "status": "OPEN",
                           "candidates": [], "agent_proposal_valid": True, "validation_reason": "",
                           "proposal": {"action": action, "settlement_ids": [], "rationale": ""}})

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            if self.down:
                return httpx.Response(503, json={"error": "unavailable"})
            return httpx.Response(200, json=[c for c in self.cases if c["status"] == "OPEN"])
        return httpx.MockTransport(handle)
