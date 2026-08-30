"""Execution engine for the deterministic first vertical slice."""

from typing import Any

from ..agents.base import AgentAdapter
from ..agents.scripted import ScriptedAgent
from ..contracts.validator import validate_input, validate_output
from ..faults.base import Fault
from ..faults.side_effects import TimeoutAfterCommitFault
from ..sandbox.server import SandboxClient
from ..sandbox.state import SandboxState
from .metrics import calculate_metrics
from .models import RunResult, Scenario, ToolCall, ToolResult
from .trace import Trace


class Runner:
    def __init__(
        self,
        contracts: dict[str, Any],
        state: SandboxState | None = None,
    ) -> None:
        self.contracts = contracts
        self.state = state or SandboxState()

    async def run(
        self,
        scenario: Scenario,
        agent: AgentAdapter | None = None,
    ) -> RunResult:
        trace = Trace()
        faults = self._build_faults(scenario)
        chosen_agent = agent or ScriptedAgent()
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
                    faults,
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
    def _build_faults(scenario: Scenario) -> list[Fault]:
        faults: list[Fault] = []
        for spec in scenario.faults:
            if spec.name == "timeout_after_commit":
                faults.append(TimeoutAfterCommitFault(spec))
            else:
                raise ValueError(f"unsupported fault in V1: {spec.name}")
        return faults

    async def _call_tool(
        self,
        client: SandboxClient,
        trace: Trace,
        faults: list[Fault],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        contract = self.contracts[tool_name]
        call = ToolCall(tool_name=tool_name, arguments=arguments)
        trace.record(
            "tool_call",
            call_id=call.call_id,
            tool=tool_name,
            arguments=arguments,
        )
        input_errors = validate_input(contract, arguments)
        if input_errors:
            for violation in input_errors:
                trace.record(
                    "schema_violation",
                    direction="input",
                    tool=tool_name,
                    call_id=call.call_id,
                    violation=violation,
                )
            result = ToolResult(
                success=False,
                error_type="schema_violation",
                error_message="; ".join(input_errors),
            )
            trace.record(
                "tool_response",
                call_id=call.call_id,
                tool=tool_name,
                success=False,
                latency_ms=result.latency_ms,
            )
            return result

        try:
            output = await client.call(tool_name, arguments)
        except Exception as exc:
            result = ToolResult(
                success=False,
                error_type="tool_error",
                error_message=str(exc),
                latency_ms=self._latency_ms(tool_name),
            )
            trace.record(
                "tool_response",
                call_id=call.call_id,
                tool=tool_name,
                success=False,
                error_type=result.error_type,
                latency_ms=result.latency_ms,
            )
            return result

        latency_ms = self._latency_ms(tool_name)
        output_errors = validate_output(contract, output)
        if output_errors:
            for violation in output_errors:
                trace.record(
                    "schema_violation",
                    direction="output",
                    tool=tool_name,
                    call_id=call.call_id,
                    violation=violation,
                )
            result = ToolResult(
                success=False,
                error_type="schema_violation",
                error_message="; ".join(output_errors),
                latency_ms=latency_ms,
            )
            trace.record(
                "tool_response",
                call_id=call.call_id,
                tool=tool_name,
                success=False,
                latency_ms=latency_ms,
            )
            return result

        if tool_name == "create_refund" and output.get("created"):
            trace.record(
                "side_effect",
                tool=tool_name,
                call_id=call.call_id,
                refund_id=output["refund"]["refund_id"],
                created=True,
            )

        for fault in faults:
            decision = fault.consider(tool_name)
            if decision:
                trace.record(
                    "fault_injected",
                    fault=decision.fault,
                    tool=decision.tool,
                    occurrence=decision.occurrence,
                )
                result = ToolResult(
                    success=False,
                    error_type="timeout",
                    error_message="request timed out after the side effect committed",
                    latency_ms=100.0,
                )
                trace.record(
                    "tool_response",
                    call_id=call.call_id,
                    tool=tool_name,
                    success=False,
                    error_type=result.error_type,
                    latency_ms=result.latency_ms,
                )
                return result

        result = ToolResult(success=True, output=output, latency_ms=latency_ms)
        trace.record(
            "tool_response",
            call_id=call.call_id,
            tool=tool_name,
            success=True,
            latency_ms=latency_ms,
        )
        return result

    @staticmethod
    def _latency_ms(tool_name: str) -> float:
        # The in-process transport is intentionally given stable logical
        # latency values so percentile metrics do not fluctuate between runs.
        return 1.0 if tool_name != "create_refund" else 2.0
