"""Core deterministic fault library."""

import asyncio
import copy

from ..core.models import FaultSpec
from .base import Fault, FaultContext, FaultOutcome, FaultStage
from .side_effects import TimeoutAfterCommitFault


class Http429Fault(Fault):
    stage = FaultStage.BEFORE_EXECUTION

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        retry_after_ms = int(self.spec.params.get("retry_after_ms", 0))
        return FaultOutcome(
            error_type="http_failure",
            error_message="rate limited",
            metadata={"status_code": 429, "retry_after_ms": retry_after_ms},
        )


class Http500Fault(Fault):
    stage = FaultStage.BEFORE_EXECUTION

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        return FaultOutcome(
            error_type="http_failure",
            error_message="simulated server failure",
            metadata={"status_code": 500},
        )


class TimeoutFault(Fault):
    stage = FaultStage.BEFORE_EXECUTION

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        return FaultOutcome(
            error_type="transport_failure",
            error_message="request timed out before tool execution",
            metadata={"ambiguous": False},
        )


class SlowResponseFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        delay_ms = float(self.spec.params.get("delay_ms", 25))
        await asyncio.sleep(delay_ms / 1000)
        return FaultOutcome(
            delay_ms=delay_ms,
            metadata={"delay_ms": delay_ms},
        )


class MalformedJsonFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        del context
        return FaultOutcome(
            response="{this is not valid JSON",
            error_type="malformed_response",
            error_message="response body is not valid JSON",
        )


class MissingRequiredFieldFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        response = copy.deepcopy(context.response)
        field = self.spec.params.get("field") or (
            context.required_fields[0] if context.required_fields else "status"
        )
        if field and isinstance(response, dict):
            response.pop(field, None)
        return FaultOutcome(
            response=response,
            metadata={"removed_field": field},
        )


class DuplicateResponseFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        response = (
            copy.deepcopy(context.previous_response)
            if context.previous_response is not None
            else copy.deepcopy(context.response)
        )
        return FaultOutcome(
            response=response,
            metadata={
                "replayed": context.previous_response is not None,
            },
        )


class StaleDataFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        response = copy.deepcopy(context.response)
        if isinstance(response, dict):
            if "status" in response:
                response["status"] = self.spec.params.get("status", "processing")
            elif "refund" in response and isinstance(response["refund"], dict):
                response["refund"]["status"] = "pending"
        return FaultOutcome(
            response=response,
            semantic_conflict=True,
            metadata={"data_state": "stale"},
        )


class ConflictingDataFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        response = copy.deepcopy(context.response)
        field = self.spec.params.get("field", "amount_cents")
        if isinstance(response, dict) and isinstance(response.get(field), int):
            response[field] += int(self.spec.params.get("delta", 1))
        return FaultOutcome(
            response=response,
            semantic_conflict=True,
            metadata={"data_state": "conflicting", "field": field},
        )


class SchemaDriftFault(Fault):
    stage = FaultStage.AFTER_RESPONSE

    async def apply(self, context: FaultContext) -> FaultOutcome:
        response = copy.deepcopy(context.response)
        field = self.spec.params.get("field", "status")
        mode = self.spec.params.get("mode", "rename")
        if isinstance(response, dict):
            if mode == "type_change" and field in response:
                response[field] = {"value": response[field]}
            elif field in response:
                response[f"{field}_changed"] = response.pop(field)
            else:
                response["data"] = {"value": response}
        return FaultOutcome(
            response=response,
            metadata={"mode": mode, "field": field},
        )


FAULT_TYPES: dict[str, type[Fault]] = {
    "http_429": Http429Fault,
    "http_500": Http500Fault,
    "timeout": TimeoutFault,
    "slow_response": SlowResponseFault,
    "malformed_json": MalformedJsonFault,
    "missing_required_field": MissingRequiredFieldFault,
    "duplicate_response": DuplicateResponseFault,
    "stale_data": StaleDataFault,
    "conflicting_data": ConflictingDataFault,
    "schema_drift": SchemaDriftFault,
    "timeout_after_commit": TimeoutAfterCommitFault,
}


def build_fault(spec: FaultSpec) -> Fault:
    try:
        return FAULT_TYPES[spec.type](spec)
    except KeyError as error:
        raise ValueError(f"unsupported fault: {spec.type}") from error
