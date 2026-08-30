"""Direct Anthropic tool-use adapter (not used by deterministic CI)."""

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
    anthropic_final_text,
    as_jsonable,
    normalize_anthropic_tool_calls,
    to_anthropic_tool_result,
    to_anthropic_tools,
)
from .prompts import SYSTEM_PROMPT


class AnthropicAgent(AgentAdapter):
    provider = "anthropic"

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
        self.model = model or os.getenv(
            "TOOLFUZZ_ANTHROPIC_MODEL",
            "claude-3-5-haiku-latest",
        )
        self.max_agent_turns = max_agent_turns
        self.trace = trace
        self.final_response = ""
        if client is not None:
            self.client = client
            return
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderConfigurationError(
                "ANTHROPIC_API_KEY is required for Anthropic runs"
            )
        try:
            from anthropic import AsyncAnthropic
        except ImportError as error:
            raise ProviderConfigurationError(
                "Anthropic support requires the 'anthropic' install extra"
            ) from error
        self.client = AsyncAnthropic(api_key=key)

    async def run(self, task: str, call_tool) -> None:
        record_provider_event(
            self.trace,
            "provider_start",
            provider=self.provider,
            model=self.model,
        )
        messages: list[Any] = [{"role": "user", "content": task}]
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
                calls = normalize_anthropic_tool_calls(response)
                response_content = getattr(response, "content", [])
                if isinstance(response, dict):
                    response_content = response.get("content", [])
                messages.append(
                    {"role": "assistant", "content": as_jsonable(response_content)}
                )
                if not calls:
                    self.final_response = anthropic_final_text(response)
                    record_provider_event(
                        self.trace,
                        "provider_complete",
                        provider=self.provider,
                        model=self.model,
                        turn=turn,
                        final_response=self.final_response,
                    )
                    return
                tool_results = []
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
                    tool_results.append(to_anthropic_tool_result(normalized, result))
                messages.append({"role": "user", "content": tool_results})
            raise MaxAgentTurnsError(
                f"Anthropic exceeded max_agent_turns={self.max_agent_turns}"
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
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=to_anthropic_tools(self.contracts),
            )
            if inspect.isawaitable(response):
                return await response
            return response
        except Exception as error:
            raise normalize_provider_exception(error) from error
