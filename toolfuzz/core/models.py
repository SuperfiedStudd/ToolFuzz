"""Typed domain models used by the runner and reporters."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ToolContract(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    has_side_effects: bool = False


class ToolCall(BaseModel):
    call_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    success: bool
    output: Any = None
    error_type: str | None = None
    error_message: str | None = None
    latency_ms: float = 0.0


class FaultSpec(BaseModel):
    name: str
    tool: str
    occurrences: int = 1
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    task: str
    faults: list[FaultSpec] = Field(default_factory=list)
    assertions: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "Scenario":
        import yaml

        with open(path, encoding="utf-8") as scenario_file:
            return cls.model_validate(yaml.safe_load(scenario_file))


class TraceEvent(BaseModel):
    event_type: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class Metrics(BaseModel):
    task_success: bool
    graceful_recovery: bool
    tool_call_correctness: float
    schema_violations: int
    invalid_retries: int
    duplicate_side_effects: int
    total_tool_calls: int
    p50_latency_ms: float
    p95_latency_ms: float


class RunResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario: Scenario
    metrics: Metrics
    events: list[TraceEvent]
    final_refund_count: int
    error: str | None = None
