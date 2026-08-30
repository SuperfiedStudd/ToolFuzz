import json
from pathlib import Path

import pytest

from toolfuzz.core.models import Scenario, ToolContract
from toolfuzz.core.runner import Runner
from toolfuzz.sandbox.state import SandboxState

ROOT = Path(__file__).parents[1]


def contracts() -> dict[str, ToolContract]:
    with (ROOT / "examples/refund_agent/tools.json").open() as tools_file:
        return {
            item["name"]: ToolContract.model_validate(item)
            for item in json.load(tools_file)
        }


@pytest.mark.asyncio
async def test_normal_refund_succeeds() -> None:
    state = SandboxState()
    scenario = Scenario(
        task="Refund ORD-104.",
        assertions={"refund_count": 1},
    )

    result = await Runner(contracts(), state).run(scenario)

    assert result.metrics.task_success is True
    assert result.metrics.graceful_recovery is True
    assert result.metrics.total_tool_calls == 2
    assert result.metrics.duplicate_side_effects == 0
    assert state.refund_count == 1


@pytest.mark.asyncio
async def test_same_idempotency_key_replays_original_refund() -> None:
    state = SandboxState()

    first, first_created = await state.create_refund("ORD-104", 4999, "same-key")
    second, second_created = await state.create_refund("ORD-104", 4999, "same-key")

    assert first_created is True
    assert second_created is False
    assert second == first
    assert state.refund_count == 1
