"""Common deterministic fault interface and injector."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..core.models import FaultSpec


class FaultStage(StrEnum):
    BEFORE_EXECUTION = "before_execution"
    AFTER_RESPONSE = "after_response"
    AFTER_COMMIT = "after_commit"


@dataclass
class FaultContext:
    tool: str
    arguments: dict[str, Any]
    response: Any = None
    previous_response: Any = None
    required_fields: list[str] = field(default_factory=list)


@dataclass
class FaultOutcome:
    response: Any = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    delay_ms: float = 0.0
    semantic_conflict: bool = False


@dataclass(frozen=True)
class FaultDecision:
    fault: "Fault"
    occurrence: int


class Fault:
    stage: FaultStage

    def __init__(self, spec: FaultSpec) -> None:
        self.spec = spec
        self._seen = 0

    def begin_call(self, tool: str) -> FaultDecision | None:
        if not self.spec.enabled or tool != self.spec.tool:
            return None
        self._seen += 1
        if self._seen == self.spec.occurrence:
            return FaultDecision(self, self._seen)
        return None

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        return FaultOutcome()


class FaultInjector:
    def __init__(self, faults: list[Fault]) -> None:
        self.faults = faults
        self._last_successful_responses: dict[str, Any] = {}

    def begin_call(self, tool: str) -> list[FaultDecision]:
        decisions = []
        for fault in self.faults:
            decision = fault.begin_call(tool)
            if decision:
                decisions.append(decision)
        return decisions

    async def apply(
        self,
        decisions: list[FaultDecision],
        stage: FaultStage,
        context: FaultContext,
    ) -> list[tuple[FaultDecision, FaultOutcome]]:
        outcomes = []
        for decision in decisions:
            if decision.fault.stage != stage:
                continue
            outcome = await decision.fault.apply(context)
            outcomes.append((decision, outcome))
        return outcomes

    def previous_response(self, tool: str) -> Any:
        return self._last_successful_responses.get(tool)

    def remember_response(self, tool: str, response: Any) -> None:
        self._last_successful_responses[tool] = response
