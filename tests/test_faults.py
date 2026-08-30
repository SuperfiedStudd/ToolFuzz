import json
from pathlib import Path

import pytest

from toolfuzz.core.models import FaultSpec, Scenario, ToolContract
from toolfuzz.core.runner import Runner
from toolfuzz.faults.base import FaultInjector
from toolfuzz.faults.library import FAULT_TYPES, build_fault
from toolfuzz.sandbox.state import SandboxState

ROOT = Path(__file__).parents[1]


def load_contracts() -> dict[str, ToolContract]:
    with (ROOT / "examples/refund_agent/tools.json").open() as tools_file:
        return {
            item["name"]: ToolContract.model_validate(item)
            for item in json.load(tools_file)
        }


@pytest.mark.parametrize("fault_type", sorted(FAULT_TYPES))
def test_fault_activates_only_on_configured_occurrence(fault_type: str) -> None:
    spec = FaultSpec(type=fault_type, tool="get_order", occurrence=2)
    injector = FaultInjector([build_fault(spec)])

    assert injector.begin_call("get_order") == []
    decisions = injector.begin_call("get_order")
    assert len(decisions) == 1
    assert decisions[0].fault.spec.type == fault_type
    assert injector.begin_call("get_order") == []


@pytest.mark.asyncio
async def test_timeout_before_execution_does_not_commit() -> None:
    class OneAttemptAgent:
        async def run(self, task, call_tool):
            del task
            await call_tool("get_order", {"order_id": "ORD-104"})
            await call_tool(
                "create_refund",
                {
                    "order_id": "ORD-104",
                    "amount_cents": 4999,
                    "idempotency_key": "single-attempt",
                },
            )

    scenario = Scenario(
        task="Refund ORD-104.",
        faults=[FaultSpec(type="timeout", tool="create_refund")],
        assertions={"refund_count": 0},
    )
    state = SandboxState()

    result = await Runner(load_contracts(), state).run(scenario, OneAttemptAgent())

    assert state.refund_count == 0
    assert result.metrics.faults_injected == 1
    assert any(
        event.metadata.get("error_type") == "transport_failure"
        for event in result.events
        if event.event_type == "tool_response"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault_type", "params", "expected_error"),
    [
        ("malformed_json", {}, "malformed_response"),
        ("missing_required_field", {"field": "created"}, "schema_violation"),
        ("schema_drift", {"field": "status"}, "schema_violation"),
    ],
)
async def test_broken_responses_are_observable(
    fault_type: str,
    params: dict[str, object],
    expected_error: str,
) -> None:
    scenario = Scenario(
        task="Refund ORD-104.",
        faults=[
            FaultSpec(
                type=fault_type,
                tool="create_refund",
                params=params,
            )
        ],
        assertions={"refund_count": 1},
    )

    result = await Runner(load_contracts()).run(scenario)

    assert result.metrics.faults_injected == 1
    assert any(
        event.metadata.get("error_type") == expected_error
        for event in result.events
        if event.event_type == "tool_response"
    )
    assert result.final_refund_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault_type", ["http_429", "http_500"])
async def test_http_failures_retry_within_policy(fault_type: str) -> None:
    scenario = Scenario(
        task="Refund ORD-104.",
        faults=[FaultSpec(type=fault_type, tool="create_refund")],
        assertions={"refund_count": 1},
    )

    result = await Runner(load_contracts()).run(scenario)

    assert result.metrics.task_success is True
    assert result.metrics.retries == 1
    assert result.metrics.invalid_retries == 0
    assert result.final_refund_count == 1


@pytest.mark.asyncio
async def test_slow_response_is_included_in_latency() -> None:
    scenario = Scenario(
        task="Refund ORD-104.",
        faults=[
            FaultSpec(
                type="slow_response",
                tool="create_refund",
                params={"delay_ms": 25},
            )
        ],
        assertions={"refund_count": 1},
    )

    result = await Runner(load_contracts()).run(scenario)

    assert result.metrics.p95_latency_ms > 20
    assert result.metrics.faults_injected == 1


@pytest.mark.asyncio
async def test_duplicate_response_replays_previous_success() -> None:
    class TwoReadsAgent:
        async def run(self, task, call_tool):
            del task
            self.first = await call_tool("get_order", {"order_id": "ORD-104"})
            self.second = await call_tool("get_order", {"order_id": "ORD-104"})

    agent = TwoReadsAgent()
    scenario = Scenario(
        task="Read order ORD-104 twice.",
        faults=[
            FaultSpec(
                type="duplicate_response",
                tool="get_order",
                occurrence=2,
            )
        ],
        assertions={"refund_count": 0},
    )

    result = await Runner(load_contracts()).run(scenario, agent)

    assert agent.first.output == agent.second.output
    assert result.metrics.faults_injected == 1


@pytest.mark.asyncio
async def test_stale_and_conflicting_reads_are_visible_and_safe() -> None:
    for fault_type in ("stale_data", "conflicting_data"):
        scenario = Scenario(
            task="Refund ORD-104.",
            faults=[FaultSpec(type=fault_type, tool="get_order")],
            assertions={"refund_count": 0},
        )
        state = SandboxState()
        result = await Runner(load_contracts(), state).run(scenario)

        assert state.refund_count == 0
        assert result.metrics.task_success is True
        assert any(
            event.event_type == "semantic_conflict" for event in result.events
        )


@pytest.mark.asyncio
async def test_invalid_retry_is_counted() -> None:
    class UnsafeAgent:
        async def run(self, task, call_tool):
            del task
            await call_tool("get_order", {"order_id": "ORD-104"})
            await call_tool(
                "create_refund",
                {
                    "order_id": "ORD-104",
                    "amount_cents": 4999,
                    "idempotency_key": "unsafe-key",
                },
            )
            await call_tool(
                "create_refund",
                {
                    "order_id": "ORD-104",
                    "amount_cents": 4999,
                    "idempotency_key": "unsafe-key",
                },
            )

    scenario = Scenario(
        task="Refund ORD-104.",
        faults=[],
        assertions={"refund_count": 1},
    )

    result = await Runner(load_contracts()).run(scenario, UnsafeAgent())

    assert result.metrics.invalid_retries == 1
    assert result.metrics.duplicate_side_effects == 0
