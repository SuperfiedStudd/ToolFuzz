import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toolfuzz.cli import app
from toolfuzz.core.models import RegressionGates, SuiteMetrics
from toolfuzz.core.suite import evaluate_gates, run_suite

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "examples/refund_agent/scenarios"


@pytest.mark.asyncio
async def test_suite_aggregates_all_refund_scenarios() -> None:
    suite = await run_suite(SCENARIOS)

    assert suite.metrics.scenarios_total == 10
    assert suite.metrics.scenarios_passed == 10
    assert suite.metrics.task_success_rate == 1.0
    assert suite.metrics.graceful_recovery_rate == 1.0
    assert suite.metrics.total_schema_violations == 2
    assert suite.metrics.total_invalid_retries == 0
    assert suite.metrics.total_duplicate_side_effects == 0
    assert suite.metrics.total_faults_injected == 9
    assert suite.metrics.total_retries == 3
    assert suite.metrics.total_recovery_attempts == 6
    assert suite.regressions == []


def test_regression_gate_reports_threshold_breach() -> None:
    metrics = SuiteMetrics(
        scenarios_passed=1,
        scenarios_total=2,
        task_success_rate=0.5,
        graceful_recovery_rate=1.0,
        total_schema_violations=0,
        total_invalid_retries=1,
        total_duplicate_side_effects=2,
        total_faults_injected=0,
        total_retries=0,
        total_recovery_attempts=0,
        p50_latency_ms=1,
        p95_latency_ms=2,
    )
    gates = RegressionGates(
        minimum_task_success_rate=1.0,
        maximum_invalid_retries=0,
        maximum_duplicate_side_effects=0,
    )

    assert evaluate_gates(metrics, gates) == [
        "minimum_task_success_rate",
        "maximum_duplicate_side_effects",
        "maximum_invalid_retries",
    ]


def test_cli_returns_nonzero_when_suite_gate_fails(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.yaml").write_text(
        "gates:\n  minimum_task_success_rate: 1.0\n",
        encoding="utf-8",
    )
    (suite_dir / "bad.yaml").write_text(
        "task: Refund order ORD-104.\nfaults: []\nassertions:\n  refund_count: 2\n",
        encoding="utf-8",
    )
    (tmp_path / "tools.json").write_text(
        (ROOT / "examples/refund_agent/tools.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["run", str(suite_dir)])

    assert result.exit_code == 1
    assert "REGRESSION / FAIL" in result.stdout


def test_cli_writes_json_report_to_nested_output_path(tmp_path: Path) -> None:
    report_path = tmp_path / "reports" / "refund.json"

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(SCENARIOS / "happy_path.yaml"),
            "--report",
            "json",
            "--output",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["metrics"]["task_success"] is True
    assert report["final_refund_count"] == 1
