"""Typed domain models used by the runner and reporters."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    metadata: dict[str, Any] = Field(default_factory=dict)


class FaultSpec(BaseModel):
    type: str = Field(
        validation_alias=AliasChoices("type", "name"),
    )
    tool: str
    occurrence: int = Field(
        default=1,
        validation_alias=AliasChoices("occurrence", "occurrences"),
        ge=1,
    )
    enabled: bool = True
    params: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("params", "config"),
    )

    model_config = ConfigDict(populate_by_name=True)

    @property
    def name(self) -> str:
        """Compatibility alias for the V1 field name."""
        return self.type


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    retryable_error_types: set[str] = Field(
        default_factory=lambda: {"transport_failure", "http_failure"},
    )
    retry_delay_ms: int = Field(default=0, ge=0)


class RegressionGates(BaseModel):
    minimum_task_success_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_graceful_recovery_rate: float | None = Field(default=None, ge=0, le=1)
    maximum_duplicate_side_effects: int | None = Field(default=None, ge=0)
    maximum_invalid_retries: int | None = Field(default=None, ge=0)


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
    faults_injected: int
    retries: int
    recovery_attempts: int


class SuiteMetrics(BaseModel):
    scenarios_passed: int
    scenarios_total: int
    task_success_rate: float
    graceful_recovery_rate: float
    total_schema_violations: int
    total_invalid_retries: int
    total_duplicate_side_effects: int
    total_faults_injected: int
    total_retries: int
    total_recovery_attempts: int
    p50_latency_ms: float
    p95_latency_ms: float


class RunResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    scenario: Scenario
    metrics: Metrics
    events: list[TraceEvent]
    final_refund_count: int
    error: str | None = None


class SuiteResult(BaseModel):
    results: list[RunResult]
    scenario_names: list[str] = Field(default_factory=list)
    metrics: SuiteMetrics
    gates: RegressionGates = Field(default_factory=RegressionGates)
    regressions: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            not self.regressions
            and self.metrics.scenarios_passed == self.metrics.scenarios_total
        )
