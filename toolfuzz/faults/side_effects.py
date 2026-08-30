"""Faults that occur after a side effect has been committed."""

from .base import Fault, FaultDecision


class TimeoutAfterCommitFault(Fault):
    name = "timeout_after_commit"

    def consider(self, tool: str) -> FaultDecision | None:
        decision = super().consider(tool)
        if decision and decision.fault != self.name:
            return None
        return decision
