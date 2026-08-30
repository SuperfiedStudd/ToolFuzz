"""Readable terminal report."""

from ..core.models import RunResult


def render(result: RunResult) -> str:
    metrics = result.metrics
    fault_names = ", ".join(
        fault.name for fault in result.scenario.faults if fault.enabled
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
