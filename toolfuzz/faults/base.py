"""Small fault interfaces used by the runner."""

from dataclasses import dataclass

from ..core.models import FaultSpec


@dataclass
class FaultDecision:
    fault: str
    tool: str
    occurrence: int


class Fault:
    def __init__(self, spec: FaultSpec) -> None:
        self.spec = spec
        self._seen = 0

    def consider(self, tool: str) -> FaultDecision | None:
        if not self.spec.enabled or tool != self.spec.tool:
            return None
        self._seen += 1
        if self._seen <= self.spec.occurrences:
            return FaultDecision(self.spec.name, tool, self._seen)
        return None
