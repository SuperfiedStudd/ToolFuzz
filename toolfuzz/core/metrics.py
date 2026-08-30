"""Deterministic metrics derived from a completed trace."""

from statistics import quantiles
from typing import Iterable

from .models import Metrics, RunResult, Scenario, SuiteMetrics
from .trace import Trace


def percentile(values: Iterable[float], percentile_value: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return round(ordered[0], 2)
    points = quantiles(ordered, n=100, method="inclusive")
    return round(points[int(percentile_value) - 1], 2)


def calculate_metrics(
    scenario: Scenario,
    trace: Trace,
    final_refund_count: int,
) -> Metrics:
    responses = trace.metadata_for("tool_response")
    latencies = [float(item["latency_ms"]) for item in responses]
    violations = trace.count("schema_violation")
    timeout_injected = any(
        event["fault"] == "timeout_after_commit"
        for event in trace.metadata_for("fault_injected")
    )
    invalid_retries = sum(
        not event.get("valid", True) for event in trace.metadata_for("retry")
    )
    duplicate_side_effects = sum(
        not event.get("created", True)
        for event in trace.metadata_for("side_effect")
    )
    task_success = final_refund_count == scenario.assertions.get("refund_count", 1)
    no_duplicates = duplicate_side_effects == 0
    graceful_recovery = (
        (not timeout_injected or task_success)
        and no_duplicates
        and trace.count("agent_complete") == 1
    )
    total_calls = trace.count("tool_call")
    correctness = (
        round((total_calls - violations) / total_calls, 2) if total_calls else 0.0
    )
    return Metrics(
        task_success=task_success,
        graceful_recovery=graceful_recovery,
        tool_call_correctness=correctness,
        schema_violations=violations,
        invalid_retries=invalid_retries,
        duplicate_side_effects=duplicate_side_effects,
        total_tool_calls=total_calls,
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
        faults_injected=trace.count("fault_injected"),
        retries=trace.count("retry"),
        recovery_attempts=trace.count("recovery_attempt"),
    )


def aggregate_metrics(results: list[RunResult]) -> SuiteMetrics:
    latencies = [
        float(event.metadata["latency_ms"])
        for result in results
        for event in result.events
        if event.event_type == "tool_response"
    ]
    passed = sum(
        result.metrics.task_success and result.metrics.graceful_recovery
        for result in results
    )
    total = len(results)
    return SuiteMetrics(
        scenarios_passed=passed,
        scenarios_total=total,
        task_success_rate=round(
            sum(result.metrics.task_success for result in results) / total, 2
        )
        if total
        else 0.0,
        graceful_recovery_rate=round(
            sum(result.metrics.graceful_recovery for result in results) / total, 2
        )
        if total
        else 0.0,
        total_schema_violations=sum(
            result.metrics.schema_violations for result in results
        ),
        total_invalid_retries=sum(
            result.metrics.invalid_retries for result in results
        ),
        total_duplicate_side_effects=sum(
            result.metrics.duplicate_side_effects for result in results
        ),
        total_faults_injected=sum(
            result.metrics.faults_injected for result in results
        ),
        total_retries=sum(result.metrics.retries for result in results),
        total_recovery_attempts=sum(
            result.metrics.recovery_attempts for result in results
        ),
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
    )
