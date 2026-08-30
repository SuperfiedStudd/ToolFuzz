"""Execution engine with staged deterministic fault injection."""

from typing import Any

from ..agents.base import AgentAdapter
from ..agents.scripted import ScriptedAgent
from ..contracts.validator import validate_input, validate_output
from ..faults.base import FaultContext, FaultInjector, FaultOutcome, FaultStage
from ..faults.library import build_fault
from ..sandbox.server import SandboxClient
from ..sandbox.state import SandboxState
from .metrics import calculate_metrics
from .models import (
    FaultSpec,
    RetryPolicy,
    RunResult,
    Scenario,
    ToolCall,
    ToolContract,
    ToolResult,
)
from .trace import Trace


class Runner:
    def __init__(
        self,
        contracts: dict[str, ToolContract],
        state: SandboxState | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.contracts = contracts
        self.state = state or SandboxState()
        self.retry_policy = retry_policy or RetryPolicy()

    async def run(
        self,
        scenario: Scenario,
        agent: AgentAdapter | None = None,
    ) -> RunResult:
        trace = Trace()
        injector = FaultInjector(self._build_faults(scenario))
        chosen_agent = agent or ScriptedAgent(retry_policy=self.retry_policy)
        history: dict[str, list[tuple[dict[str, Any], ToolResult]]] = {}
        trace.record("agent_start", task=scenario.task)
        error: str | None = None

        async with SandboxClient(self.state) as client:
            async def call_tool(
                tool_name: str,
                arguments: dict[str, Any],
            ) -> ToolResult:
                return await self._call_tool(
                    client,
                    trace,
                    injector,
                    history,
                    tool_name,
                    arguments,
                )

            try:
                await chosen_agent.run(scenario.task, call_tool)
            except Exception as exc:  # pragma: no cover - defensive boundary
                error = str(exc)

        trace.record(
            "agent_complete",
            success=error is None,
            final_refund_count=self.state.refund_count,
        )
        metrics = calculate_metrics(scenario, trace, self.state.refund_count)
        if error:
            metrics.task_success = False
            metrics.graceful_recovery = False
        return RunResult(
            scenario=scenario,
            metrics=metrics,
            events=trace.events,
            final_refund_count=self.state.refund_count,
            error=error,
        )

    @staticmethod
    def _build_faults(scenario: Scenario) -> list[Any]:
        return [build_fault(spec) for spec in scenario.faults]

    async def _call_tool(
        self,
        client: SandboxClient,
        trace: Trace,
        injector: FaultInjector,
        history: dict[str, list[tuple[dict[str, Any], ToolResult]]],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        contract = self.contracts[tool_name]
        call = ToolCall(tool_name=tool_name, arguments=arguments)
        previous_calls = history.get(tool_name, [])
        if any(not result.success for calls in history.values() for _, result in calls):
            trace.record(
                "recovery_attempt",
                tool=tool_name,
                call_id=call.call_id,
            )
        trace.record(
            "tool_call",
            call_id=call.call_id,
            tool=tool_name,
            arguments=arguments,
        )
        input_errors = validate_input(contract, arguments)
        if input_errors:
            result = self._schema_failure(
                trace,
                call,
                input_errors,
                direction="input",
            )
            self._record_retry(trace, history, contract, call, result)
            history.setdefault(tool_name, []).append((arguments, result))
            return result

        decisions = injector.begin_call(tool_name)
        before_context = FaultContext(tool_name, arguments)
        before_outcomes = await injector.apply(
            decisions,
            FaultStage.BEFORE_EXECUTION,
            before_context,
        )
        if before_outcomes:
            result = self._fault_failure(
                trace,
                call,
                before_outcomes,
                latency_ms=0.0,
            )
            self._record_retry(trace, history, contract, call, result)
            history.setdefault(tool_name, []).append((arguments, result))
            return result

        try:
            service_output = await client.call(tool_name, arguments)
        except Exception as exc:
            result = ToolResult(
                success=False,
                error_type="transport_failure",
                error_message=str(exc),
                latency_ms=self._latency_ms(tool_name),
            )
            self._record_response(trace, call, result)
            self._record_retry(trace, history, contract, call, result)
            history.setdefault(tool_name, []).append((arguments, result))
            return result

        context = FaultContext(
            tool_name,
            arguments,
            response=service_output,
            previous_response=injector.previous_response(tool_name),
            required_fields=contract.output_schema.get("required", []),
        )
        after_outcomes = await injector.apply(
            decisions,
            FaultStage.AFTER_RESPONSE,
            context,
        )
        output = service_output
        latency_ms = self._latency_ms(tool_name)
        injected_failure: FaultOutcome | None = None
        for decision, outcome in after_outcomes:
            self._record_fault(trace, decision.fault.spec, decision.occurrence)
            if outcome.semantic_conflict:
                trace.record(
                    "semantic_conflict",
                    tool=tool_name,
                    fault=decision.fault.spec.type,
                    **outcome.metadata,
                )
            if outcome.delay_ms:
                latency_ms += outcome.delay_ms
            if outcome.response is not None:
                output = outcome.response
            if outcome.error_type:
                injected_failure = outcome
        injector.remember_response(tool_name, service_output)
        if tool_name == "create_refund" and service_output.get("created"):
            trace.record(
                "side_effect",
                tool=tool_name,
                call_id=call.call_id,
                refund_id=service_output["refund"]["refund_id"],
                created=True,
            )
        if injected_failure:
            result = self._fault_failure(
                trace,
                call,
                [(None, injected_failure)],
                latency_ms=latency_ms,
                record_fault=False,
            )
            self._record_retry(trace, history, contract, call, result)
            history.setdefault(tool_name, []).append((arguments, result))
            return result

        after_commit_outcomes = await injector.apply(
            decisions,
            FaultStage.AFTER_COMMIT,
            context,
        )
        if after_commit_outcomes:
            result = self._fault_failure(
                trace,
                call,
                after_commit_outcomes,
                latency_ms=100.0,
            )
            self._record_retry(trace, history, contract, call, result)
            history.setdefault(tool_name, []).append((arguments, result))
            return result

        output_errors = validate_output(contract, output)
        if output_errors:
            result = self._schema_failure(
                trace,
                call,
                output_errors,
                direction="output",
                latency_ms=latency_ms,
            )
        else:
            result = ToolResult(
                success=True,
                output=output,
                latency_ms=latency_ms,
            )
            self._record_response(trace, call, result)
        self._record_retry(trace, history, contract, call, result)
        history.setdefault(tool_name, []).append((arguments, result))
        return result

    @staticmethod
    def _record_fault(trace: Trace, spec: FaultSpec, occurrence: int) -> None:
        trace.record(
            "fault_injected",
            fault=spec.type,
            tool=spec.tool,
            occurrence=occurrence,
            params=spec.params,
        )

    def _fault_failure(
        self,
        trace: Trace,
        call: ToolCall,
        outcomes: list[tuple[Any, FaultOutcome]],
        latency_ms: float,
        record_fault: bool = True,
    ) -> ToolResult:
        outcome = outcomes[0][1]
        if record_fault:
            for decision, _ in outcomes:
                if decision:
                    self._record_fault(
                        trace,
                        decision.fault.spec,
                        decision.occurrence,
                    )
        result = ToolResult(
            success=False,
            error_type=outcome.error_type or "transport_failure",
            error_message=outcome.error_message,
            latency_ms=latency_ms,
            metadata=outcome.metadata,
        )
        self._record_response(trace, call, result)
        return result

    @staticmethod
    def _schema_failure(
        trace: Trace,
        call: ToolCall,
        errors: list[str],
        direction: str,
        latency_ms: float = 0.0,
    ) -> ToolResult:
        for violation in errors:
            trace.record(
                "schema_violation",
                direction=direction,
                tool=call.tool_name,
                call_id=call.call_id,
                violation=violation,
            )
        result = ToolResult(
            success=False,
            error_type="schema_violation",
            error_message="; ".join(errors),
            latency_ms=latency_ms,
        )
        Runner._record_response(trace, call, result)
        return result

    @staticmethod
    def _record_response(trace: Trace, call: ToolCall, result: ToolResult) -> None:
        trace.record(
            "tool_response",
            call_id=call.call_id,
            tool=call.tool_name,
            success=result.success,
            error_type=result.error_type,
            latency_ms=result.latency_ms,
            **result.metadata,
        )

    def _record_retry(
        self,
        trace: Trace,
        history: dict[str, list[tuple[dict[str, Any], ToolResult]]],
        contract: ToolContract,
        call: ToolCall,
        result: ToolResult,
    ) -> None:
        previous = history.get(call.tool_name, [])
        if not previous:
            return
        prior_arguments, prior_result = previous[-1]
        attempt = len(previous) + 1
        valid = True
        reason = "retryable_failure"
        if prior_result.success:
            valid, reason = False, "retry_after_confirmed_success"
        elif attempt > self.retry_policy.max_attempts:
            valid, reason = False, "retry_limit_exceeded"
        elif prior_result.error_type not in self.retry_policy.retryable_error_types:
            valid, reason = False, "non_retryable_failure"
        elif (
            contract.has_side_effects
            and prior_result.metadata.get("ambiguous")
            and prior_arguments.get("idempotency_key")
            != call.arguments.get("idempotency_key")
        ):
            valid, reason = False, "changed_idempotency_key_after_ambiguous_failure"
        trace.record(
            "retry",
            tool=call.tool_name,
            call_id=call.call_id,
            attempt=attempt,
            valid=valid,
            reason=reason,
        )

    @staticmethod
    def _latency_ms(tool_name: str) -> float:
        # Stable logical values keep percentile metrics reproducible.
        return 1.0 if tool_name != "create_refund" else 2.0
