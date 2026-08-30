"""Scenario discovery, suite execution, and regression gates."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from ..agents.base import AgentAdapter
from ..core.models import (
    RegressionGates,
    Scenario,
    SuiteResult,
    ToolContract,
)
from .metrics import aggregate_metrics
from .runner import Runner


def load_contracts(path: Path) -> dict[str, ToolContract]:
    with path.open(encoding="utf-8") as tools_file:
        raw_contracts = json.load(tools_file)
    return {
        contract.name: contract
        for contract in (ToolContract.model_validate(item) for item in raw_contracts)
    }


def load_gates(directory: Path) -> RegressionGates:
    config_path = directory / "suite.yaml"
    if not config_path.exists():
        return RegressionGates()
    with config_path.open(encoding="utf-8") as config_file:
        config: dict[str, Any] = yaml.safe_load(config_file) or {}
    return RegressionGates.model_validate(config.get("gates", config))


async def run_suite(
    directory: Path,
    agent_factory: Callable[[dict[str, ToolContract]], AgentAdapter] | None = None,
) -> SuiteResult:
    scenario_paths = sorted(
        path for path in directory.glob("*.yaml") if path.name != "suite.yaml"
    )
    if not scenario_paths:
        raise ValueError(f"no scenario YAML files found in {directory}")
    contracts = load_contracts(directory.parent / "tools.json")
    results = []
    for scenario_path in scenario_paths:
        stateful_runner = Runner(contracts)
        agent = agent_factory(contracts) if agent_factory else None
        results.append(
            await stateful_runner.run(
                Scenario.from_yaml(str(scenario_path)),
                agent=agent,
            )
        )
    metrics = aggregate_metrics(results)
    gates = load_gates(directory)
    regressions = evaluate_gates(metrics, gates)
    if metrics.scenarios_passed < metrics.scenarios_total:
        regressions.insert(0, "scenario_failure")
    return SuiteResult(
        results=results,
        scenario_names=[path.stem for path in scenario_paths],
        metrics=metrics,
        gates=gates,
        regressions=regressions,
    )


def evaluate_gates(metrics: Any, gates: RegressionGates) -> list[str]:
    regressions: list[str] = []
    if (
        gates.minimum_task_success_rate is not None
        and metrics.task_success_rate < gates.minimum_task_success_rate
    ):
        regressions.append("minimum_task_success_rate")
    if (
        gates.minimum_graceful_recovery_rate is not None
        and metrics.graceful_recovery_rate < gates.minimum_graceful_recovery_rate
    ):
        regressions.append("minimum_graceful_recovery_rate")
    if (
        gates.maximum_duplicate_side_effects is not None
        and metrics.total_duplicate_side_effects > gates.maximum_duplicate_side_effects
    ):
        regressions.append("maximum_duplicate_side_effects")
    if (
        gates.maximum_invalid_retries is not None
        and metrics.total_invalid_retries > gates.maximum_invalid_retries
    ):
        regressions.append("maximum_invalid_retries")
    return regressions
