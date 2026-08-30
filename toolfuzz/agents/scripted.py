"""Deterministic refund agent used for the first vertical slice."""

import asyncio
from typing import Any

from ..core.models import RetryPolicy
from .base import AgentAdapter, ToolCaller


class ScriptedAgent(AgentAdapter):
    def __init__(
        self,
        order_id: str = "ORD-104",
        amount_cents: int = 4999,
        idempotency_key: str = "toolfuzz-refund-ORD-104",
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.order_id = order_id
        self.amount_cents = amount_cents
        self.idempotency_key = idempotency_key
        self.retry_policy = retry_policy or RetryPolicy()
        self.refund: dict[str, Any] | None = None

    async def run(self, task: str, call_tool: ToolCaller) -> None:
        del task
        order_result = await call_tool("get_order", {"order_id": self.order_id})
        if not order_result.success or not self._order_is_refundable(
            order_result.output
        ):
            return
        create_arguments = {
            "order_id": self.order_id,
            "amount_cents": self.amount_cents,
            "idempotency_key": self.idempotency_key,
        }
        for attempt in range(self.retry_policy.max_attempts):
            create_result = await call_tool("create_refund", create_arguments)
            if create_result.success:
                self.refund = create_result.output["refund"]
                return
            if create_result.error_type in self.retry_policy.retryable_error_types:
                if attempt + 1 < self.retry_policy.max_attempts:
                    if self.retry_policy.retry_delay_ms:
                        await asyncio.sleep(self.retry_policy.retry_delay_ms / 1000)
                    continue
            # An ambiguous response may have committed the refund. Read
            # authoritative state before considering any further side effect.
            if create_result.metadata.get("ambiguous") or create_result.error_type in {
                "malformed_response",
                "schema_violation",
            }:
                await self._read_refund(call_tool)
            return

    def _order_is_refundable(self, order: Any) -> bool:
        return (
            isinstance(order, dict)
            and order.get("status") == "delivered"
            and order.get("amount_cents") == self.amount_cents
        )

    async def _read_refund(self, call_tool: ToolCaller) -> None:
        status_result = await call_tool("get_refund", {"order_id": self.order_id})
        if not status_result.success:
            return
        refund = status_result.output.get("refund")
        if isinstance(refund, dict) and refund.get("amount_cents") == self.amount_cents:
            self.refund = refund
