"""Agent adapter interface."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.models import ToolResult
from ..core.trace import Trace

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


class ProviderError(RuntimeError):
    """Normalized failure from a model provider."""

    error_type = "provider_error"


class ProviderConfigurationError(ProviderError):
    error_type = "provider_configuration"


class ProviderAuthenticationError(ProviderError):
    error_type = "provider_authentication"


class ProviderRateLimitError(ProviderError):
    error_type = "provider_rate_limit"


class ProviderTimeoutError(ProviderError):
    error_type = "provider_timeout"


class ProviderResponseError(ProviderError):
    error_type = "provider_response"


class MaxAgentTurnsError(ProviderError):
    error_type = "max_agent_turns_exceeded"


class AgentAdapter(ABC):
    provider: str = "unknown"

    @abstractmethod
    async def run(self, task: str, call_tool: ToolCaller) -> None:
        """Run a task using the supplied tool caller."""


def record_provider_event(
    trace: Trace | None,
    event_type: str,
    *,
    provider: str,
    model: str,
    **metadata: Any,
) -> None:
    if trace is not None:
        trace.record(
            event_type,
            provider=provider,
            model=model,
            **metadata,
        )


def normalize_provider_exception(error: Exception) -> ProviderError:
    """Map common SDK exception shapes without importing provider SDKs."""
    if isinstance(error, ProviderError):
        return error
    status_code = getattr(error, "status_code", None)
    name = type(error).__name__.lower()
    message = str(error)
    if status_code in {401, 403} or "auth" in name or "api_key" in name:
        return ProviderAuthenticationError(message)
    if status_code == 429 or "rate" in name:
        return ProviderRateLimitError(message)
    if "timeout" in name or isinstance(error, TimeoutError):
        return ProviderTimeoutError(message)
    return ProviderResponseError(message)
