"""In-memory state for the refund sandbox."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Refund:
    refund_id: str
    order_id: str
    amount_cents: int
    status: str = "created"

    def as_dict(self) -> dict[str, object]:
        return {
            "refund_id": self.refund_id,
            "order_id": self.order_id,
            "amount_cents": self.amount_cents,
            "status": self.status,
        }


class SandboxState:
    def __init__(self) -> None:
        self.orders: dict[str, dict[str, object]] = {
            "ORD-104": {
                "order_id": "ORD-104",
                "status": "delivered",
                "amount_cents": 4999,
            }
        }
        self.refunds: dict[str, Refund] = {}
        self.idempotency_keys: dict[str, str] = {}
        self._next_refund_number = 1

    async def get_order(self, order_id: str) -> dict[str, object]:
        if order_id not in self.orders:
            raise KeyError(f"order not found: {order_id}")
        return self.orders[order_id]

    async def get_refund(self, order_id: str) -> dict[str, object] | None:
        refund = self.refunds.get(order_id)
        return refund.as_dict() if refund else None

    async def create_refund(
        self,
        order_id: str,
        amount_cents: int,
        idempotency_key: str,
    ) -> tuple[dict[str, object], bool]:
        await self.get_order(order_id)
        existing_id = self.idempotency_keys.get(idempotency_key)
        if existing_id:
            return self.refunds[existing_id].as_dict(), False
        if order_id in self.refunds:
            raise ValueError(f"refund already exists for order: {order_id}")

        refund_id = f"REF-{self._next_refund_number:03d}"
        self._next_refund_number += 1
        refund = Refund(refund_id, order_id, amount_cents)
        self.refunds[order_id] = refund
        self.idempotency_keys[idempotency_key] = order_id
        return refund.as_dict(), True

    @property
    def refund_count(self) -> int:
        return len(self.refunds)
