"""Direct Google GenAI tool-calling adapter."""

import inspect
import os
from typing import Any

from ..core.models import ToolContract, ToolResult
from ..core.trace import Trace
from .base import (
    AgentAdapter,
    MaxAgentTurnsError,
    ProviderConfigurationError,
    normalize_provider_exception,
    record_provider_event,
)
from .prompts import SYSTEM_PROMPT
from .normalization import (
    gemini_final_text,
    normalize_gemini_tool_calls,
    to_gemini_tool_result,
    to_gemini_tools,
)

class GeminiAgent(AgentAdapter):
    provider = "gemini"

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
            "TOOLFUZZ_GEMINI_MODEL",
            "gemini-3.6-flash",
        )
        self.max_agent_turns = max_agent_turns
        self.trace = trace
        self.final_response = ""
        if client is not None:
            self.client = client
            return
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ProviderConfigurationError(
                "GEMINI_API_KEY is required for Gemini runs"
            )
        try:
            from google import genai
        except ImportError as error:
            raise ProviderConfigurationError(
                "Gemini support requires the 'gemini' install extra"
            ) from error
        self.client = genai.Client(api_key=key)
        self._api_key = key

    async def run(self, task: str, call_tool) -> None:
        record_provider_event(
            self.trace,
            "provider_start",
            provider=self.provider,
            model=self.model,
        )
        contents: list[Any] = [
            {"role": "user", "parts": [{"text": task}]},
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
                response = await self._generate(contents)
                calls = normalize_gemini_tool_calls(response)
                if not calls:
                    self.final_response = self._safe_text(gemini_final_text(response))
                    record_provider_event(
                        self.trace,
                        "provider_complete",
                        provider=self.provider,
                        model=self.model,
                        turn=turn,
                        final_response=self.final_response,
                    )
                    return
                contents.append(self._response_content(response))
                tool_parts = []
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
                    tool_parts.append(to_gemini_tool_result(normalized, result))
                contents.append({"role": "user", "parts": tool_parts})
            raise MaxAgentTurnsError(
                f"Gemini exceeded max_agent_turns={self.max_agent_turns}"
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

    async def _generate(self, contents: list[Any]) -> Any:
        try:
            service = getattr(self.client, "aio", self.client)
            models = getattr(service, "models", service)
            response = models.generate_content(
                model=self.model,
                contents=contents,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "tools": to_gemini_tools(self.contracts),
                },
            )
            if inspect.isawaitable(response):
                return await response
            return response
        except Exception as error:
            raise normalize_provider_exception(error) from error

    @staticmethod
    def _response_content(response: Any) -> Any:
        candidates = (
            response.get("candidates", [])
            if isinstance(response, dict)
            else getattr(response, "candidates", [])
        )
        if candidates:
            candidate = candidates[0]
            return (
                candidate.get("content", {})
                if isinstance(candidate, dict)
                else getattr(candidate, "content", {})
            )
        return {"role": "model", "parts": []}

    def _safe_text(self, text: str) -> str:
        key = getattr(self, "_api_key", "")
        return text.replace(key, "[REDACTED]") if key else text
