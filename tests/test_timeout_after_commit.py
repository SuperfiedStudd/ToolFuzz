import json
from pathlib import Path

import pytest

from toolfuzz.core.models import FaultSpec, Scenario, ToolContract
from toolfuzz.core.runner import Runner
from toolfuzz.sandbox.state import SandboxState

ROOT = Path(__file__).parents[1]


def load_contracts() -> dict[str, ToolContract]:
    with (ROOT / "examples/refund_agent/tools.json").open() as tools_file:
        return {
            item["name"]: ToolContract.model_validate(item)
            for item in json.load(tools_file)
        }


@pytest.mark.asyncio
async def test_timeout_after_commit_recovers_without_duplicate() -> None:
    state = SandboxState()
    scenario = Scenario(
        task="Refund ORD-104.",
        faults=[
            FaultSpec(
                name="timeout_after_commit",
                tool="create_refund",
            )
        ],
        assertions={"refund_count": 1, "no_duplicate_side_effects": True},
    )

    result = await Runner(load_contracts(), state).run(scenario)

    assert any(
        event.event_type == "fault_injected"
        and event.metadata["fault"] == "timeout_after_commit"
        for event in result.events
    )
    assert state.refund_count == 1
    assert result.metrics.task_success is True
    assert result.metrics.graceful_recovery is True
    assert result.metrics.duplicate_side_effects == 0
    assert result.metrics.schema_violations == 0
    assert result.metrics.total_tool_calls == 3
    assert result.metrics.p50_latency_ms == 1.0
    assert result.metrics.p95_latency_ms == 90.1
