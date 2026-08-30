"""Agent adapter interface."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.models import ToolResult

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


class AgentAdapter(ABC):
    @abstractmethod
    async def run(self, task: str, call_tool: ToolCaller) -> None:
        """Run a task using the supplied tool caller."""
