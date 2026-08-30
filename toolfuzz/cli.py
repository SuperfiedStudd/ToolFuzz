"""Command-line interface for ToolFuzz."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from .agents.factory import create_agent
from .agents.base import ProviderError
from .core.models import Scenario, SuiteResult
from .core.runner import Runner
from .core.suite import load_contracts, run_suite
from .reporters.console import render as render_console
from .reporters.json import render as render_json

app = typer.Typer(help="Adversarial reliability testing for tool-using AI agents.")


@app.command()
def run(
    scenario_path: Annotated[
        Path,
        typer.Argument(exists=True, readable=True),
    ],
    report: Annotated[
        str,
        typer.Option("--report", help="Report format: console or json."),
    ] = "console",
    provider: Annotated[
        str,
        typer.Option("--provider", help="scripted, gemini, openai, or anthropic."),
    ] = "scripted",
    model: Annotated[
        str | None,
        typer.Option("--model", help="Optional provider model override."),
    ] = None,
) -> None:
    """Run one YAML scenario or every scenario in a directory."""
    if report not in {"console", "json"}:
        raise typer.BadParameter("must be 'console' or 'json'")
    try:
        if scenario_path.is_dir():
            result = asyncio.run(
                run_suite(
                    scenario_path,
                    agent_factory=lambda contracts: create_agent(
                        provider,
                        contracts,
                        model=model,
                    ),
                )
            )
        else:
            scenario = Scenario.from_yaml(str(scenario_path))
            contracts = load_contracts(scenario_path.parent / "tools.json")
            agent = create_agent(provider, contracts, model=model)
            result = asyncio.run(Runner(contracts).run(scenario, agent=agent))
    except (ProviderError, ValueError) as error:
        typer.echo(f"Provider configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(render_json(result) if report == "json" else render_console(result))
    if isinstance(result, SuiteResult) and result.regressions:
        raise typer.Exit(code=1)
    if not isinstance(result, SuiteResult) and result.error:
        raise typer.Exit(code=1)


@app.command(name="live-test")
def live_test(
    provider: Annotated[
        str,
        typer.Argument(help="Provider to validate; currently only gemini."),
    ] = "gemini",
    model: Annotated[
        str | None,
        typer.Option("--model", help="Optional Gemini model override."),
    ] = None,
) -> None:
    """Run exactly the two documented Gemini smoke scenarios."""
    if provider.lower() != "gemini":
        raise typer.BadParameter("live-test currently supports only gemini")
    scenario_root = Path("examples/refund_agent")
    contracts = load_contracts(scenario_root / "tools.json")
    paths = [
        scenario_root / "scenarios" / "happy_path.yaml",
        scenario_root / "scenarios" / "timeout_after_commit.yaml",
    ]
    try:
        for path in paths:
            agent = create_agent("gemini", contracts, model=model)
            result = asyncio.run(
                Runner(contracts).run(Scenario.from_yaml(str(path)), agent=agent)
            )
            typer.echo(render_console(result))
            if (
                result.error
                or not result.metrics.task_success
                or not result.metrics.graceful_recovery
                or result.metrics.duplicate_side_effects
            ):
                raise typer.Exit(code=1)
    except ProviderError as error:
        typer.echo(f"Gemini configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error


@app.command()
def version() -> None:
    """Print the installed ToolFuzz version."""
    from . import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
