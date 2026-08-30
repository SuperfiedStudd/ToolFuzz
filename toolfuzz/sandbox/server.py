"""FastAPI REST service and in-process async client for the sandbox."""

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .state import SandboxState


class RefundRequest(BaseModel):
    order_id: str
    amount_cents: int
    idempotency_key: str


def create_app(state: SandboxState) -> FastAPI:
    app = FastAPI(title="ToolFuzz Refund Sandbox")

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str) -> dict[str, object]:
        try:
            return await state.get_order(order_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/refunds/{order_id}")
    async def get_refund(order_id: str) -> dict[str, Any]:
        refund = await state.get_refund(order_id)
        return {"refund": refund}

    @app.post("/refunds")
    async def create_refund(request: RefundRequest) -> dict[str, Any]:
        try:
            refund, created = await state.create_refund(
                request.order_id,
                request.amount_cents,
                request.idempotency_key,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"refund": refund, "created": created}

    return app


class SandboxClient:
    """HTTPX client using the FastAPI app through an in-process transport."""

    def __init__(self, state: SandboxState) -> None:
        self.state = state
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SandboxClient":
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(self.state)),
            base_url="http://sandbox",
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self._client is None:
            raise RuntimeError("SandboxClient must be used as an async context manager")
        if tool_name == "get_order":
            response = await self._client.get(
                f"/orders/{arguments['order_id']}",
            )
            return await self._json_or_raise(response)
        if tool_name == "get_refund":
            response = await self._client.get(
                f"/refunds/{arguments['order_id']}",
            )
            return await self._json_or_raise(response)
        if tool_name == "create_refund":
            response = await self._client.post("/refunds", json=arguments)
            return await self._json_or_raise(response)
        raise ValueError(f"unknown tool: {tool_name}")

    @staticmethod
    async def _json_or_raise(response: httpx.Response) -> Any:
        if response.is_error:
            detail = response.json().get("detail", response.text)
            raise RuntimeError(str(detail))
        return response.json()
