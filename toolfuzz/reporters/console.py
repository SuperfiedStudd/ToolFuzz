"""Readable terminal report."""

from ..core.models import RunResult, SuiteResult


def render(result: RunResult | SuiteResult) -> str:
    if isinstance(result, SuiteResult):
        return render_suite(result)
    metrics = result.metrics
    fault_names = ", ".join(
        fault.type for fault in result.scenario.faults if fault.enabled
    ) or "none"
    status = "PASS" if metrics.task_success and metrics.graceful_recovery else "FAIL"
    lines = [
        "ToolFuzz run",
        f"  Scenario: {result.scenario.task}",
        f"  Injected fault: {fault_names}",
        f"  Result: {status}",
        "",
        "Metrics:",
        f"  task_success: {metrics.task_success}",
        f"  graceful_recovery: {metrics.graceful_recovery}",
        f"  tool_call_correctness: {metrics.tool_call_correctness:.2f}",
        f"  schema_violations: {metrics.schema_violations}",
        f"  invalid_retries: {metrics.invalid_retries}",
        f"  duplicate_side_effects: {metrics.duplicate_side_effects}",
        f"  total_tool_calls: {metrics.total_tool_calls}",
        f"  p50_latency_ms: {metrics.p50_latency_ms:.2f}",
        f"  p95_latency_ms: {metrics.p95_latency_ms:.2f}",
        f"  final_refund_count: {result.final_refund_count}",
    ]
    if result.error:
        lines.extend(["", f"Error: {result.error}"])
    return "\n".join(lines)


def render_suite(result: SuiteResult) -> str:
    lines = [
        "ToolFuzz Regression Suite",
        "",
        "Scenario                     Fault                  Result",
        "----------------------------------------------------------",
    ]
    for name, scenario_result in zip(
        result.scenario_names,
        result.results,
        strict=True,
    ):
        faults = ", ".join(
            fault.type for fault in scenario_result.scenario.faults if fault.enabled
        ) or "none"
        status = (
            "PASS"
            if scenario_result.metrics.task_success
            and scenario_result.metrics.graceful_recovery
            else "FAIL"
        )
        lines.append(f"{name:<28}{faults:<23}{status}")
    metrics = result.metrics
    lines.extend(
        [
            "",
            f"{metrics.scenarios_passed}/{metrics.scenarios_total} scenarios passed",
            "",
            f"Task success rate          {metrics.task_success_rate:.0%}",
            f"Graceful recovery rate     {metrics.graceful_recovery_rate:.0%}",
            f"Schema violations          {metrics.total_schema_violations}",
            f"Invalid retries            {metrics.total_invalid_retries}",
            f"Duplicate side effects     {metrics.total_duplicate_side_effects}",
            f"Faults injected            {metrics.total_faults_injected}",
            f"Retries                    {metrics.total_retries}",
            f"Recovery attempts          {metrics.total_recovery_attempts}",
            f"p95 latency                {metrics.p95_latency_ms:.2f} ms",
        ]
    )
    if result.regressions:
        lines.extend(["", "REGRESSION / FAIL", *result.regressions])
    else:
        lines.extend(["", "PASS"])
    return "\n".join(lines)
