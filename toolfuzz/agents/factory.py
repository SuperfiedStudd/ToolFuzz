"""Provider selection without coupling the core runner to SDKs."""

from typing import Any

from ..core.models import ToolContract
from .anthropic import AnthropicAgent
from .base import AgentAdapter
from .gemini import GeminiAgent
from .openai import OpenAIAgent
from .scripted import ScriptedAgent


def create_agent(
    provider: str,
    contracts: dict[str, ToolContract],
    *,
    model: str | None = None,
    trace: Any | None = None,
) -> AgentAdapter:
    provider = provider.lower()
    contract_list = list(contracts.values())
    if provider == "scripted":
        return ScriptedAgent()
    if provider == "gemini":
        return GeminiAgent(contract_list, model=model, trace=trace)
    if provider == "openai":
        return OpenAIAgent(contract_list, model=model, trace=trace)
    if provider == "anthropic":
        return AnthropicAgent(contract_list, model=model, trace=trace)
    raise ValueError(f"unsupported provider: {provider}")
