"""Faults that occur after a side effect has been committed."""

from .base import Fault, FaultContext, FaultOutcome, FaultStage


class TimeoutAfterCommitFault(Fault):
    stage = FaultStage.AFTER_COMMIT

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        return FaultOutcome(
            error_type="transport_failure",
            error_message="request timed out after the side effect committed",
            metadata={"ambiguous": True},
        )
