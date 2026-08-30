"""Direct OpenAI tool-calling adapter (not used by deterministic CI)."""

import inspect
import os
from typing import Any

from ..core.models import ToolContract
from ..core.trace import Trace
from .base import (
    AgentAdapter,
    MaxAgentTurnsError,
    ProviderConfigurationError,
    normalize_provider_exception,
    record_provider_event,
)
from .normalization import (
    as_jsonable,
    normalize_openai_tool_calls,
    openai_final_text,
    to_openai_tool_result,
    to_openai_tools,
)
from .prompts import SYSTEM_PROMPT


class OpenAIAgent(AgentAdapter):
    provider = "openai"

    def __init__(
        self,
        contracts: list[ToolContract],
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
        max_agent_turns: int = 12,
        trace: Trace | None = None,
    ) -> None:
        self.contracts = contracts
        self.model = model or os.getenv("TOOLFUZZ_OPENAI_MODEL", "gpt-4o-mini")
        self.max_agent_turns = max_agent_turns
        self.trace = trace
        self.final_response = ""
        if client is not None:
            self.client = client
            return
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required for OpenAI runs"
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as error:
            raise ProviderConfigurationError(
                "OpenAI support requires the 'openai' install extra"
            ) from error
        self.client = AsyncOpenAI(api_key=key)

    async def run(self, task: str, call_tool) -> None:
        record_provider_event(
            self.trace,
            "provider_start",
            provider=self.provider,
            model=self.model,
        )
        messages: list[Any] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        try:
            for turn in range(1, self.max_agent_turns + 1):
                record_provider_event(
                    self.trace,
                    "provider_turn",
                    provider=self.provider,
                    model=self.model,
                    turn=turn,
                )
                response = await self._generate(messages)
                message = response.choices[0].message
                calls = normalize_openai_tool_calls(message)
                messages.append(as_jsonable(message))
                if not calls:
                    self.final_response = openai_final_text(message)
                    record_provider_event(
                        self.trace,
                        "provider_complete",
                        provider=self.provider,
                        model=self.model,
                        turn=turn,
                        final_response=self.final_response,
                    )
                    return
                for normalized in calls:
                    record_provider_event(
                        self.trace,
                        "provider_tool_request",
                        provider=self.provider,
                        model=self.model,
                        turn=turn,
                        tool=normalized.call.tool_name,
                    )
                    result = await call_tool(
                        normalized.call.tool_name,
                        normalized.call.arguments,
                    )
                    messages.append(to_openai_tool_result(normalized, result))
            raise MaxAgentTurnsError(
                f"OpenAI exceeded max_agent_turns={self.max_agent_turns}"
            )
        except Exception as error:
            normalized_error = normalize_provider_exception(error)
            record_provider_event(
                self.trace,
                "provider_error",
                provider=self.provider,
                model=self.model,
                error_type=normalized_error.error_type,
                message=str(normalized_error),
            )
            raise normalized_error from error

    async def _generate(self, messages: list[Any]) -> Any:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=to_openai_tools(self.contracts),
                tool_choice="auto",
            )
            if inspect.isawaitable(response):
                return await response
            return response
        except Exception as error:
            raise normalize_provider_exception(error) from error
