"""Deterministic refund agent used for the first vertical slice."""

from typing import Any

from .base import AgentAdapter, ToolCaller


class ScriptedAgent(AgentAdapter):
    def __init__(
        self,
        order_id: str = "ORD-104",
        amount_cents: int = 4999,
        idempotency_key: str = "toolfuzz-refund-ORD-104",
    ) -> None:
        self.order_id = order_id
        self.amount_cents = amount_cents
        self.idempotency_key = idempotency_key
        self.refund: dict[str, Any] | None = None

    async def run(self, task: str, call_tool: ToolCaller) -> None:
        del task
        order_result = await call_tool("get_order", {"order_id": self.order_id})
        if not order_result.success:
            return
        create_result = await call_tool(
            "create_refund",
            {
                "order_id": self.order_id,
                "amount_cents": self.amount_cents,
                "idempotency_key": self.idempotency_key,
            },
        )
        if create_result.success:
            self.refund = create_result.output["refund"]
            return

        # A timeout after commit is ambiguous. Read the authoritative state
        # before retrying, avoiding a second side effect.
        status_result = await call_tool("get_refund", {"order_id": self.order_id})
        if status_result.success:
            self.refund = status_result.output.get("refund")
