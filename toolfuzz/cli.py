"""Command-line interface for ToolFuzz."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

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
) -> None:
    """Run one YAML scenario or every scenario in a directory."""
    if report not in {"console", "json"}:
        raise typer.BadParameter("must be 'console' or 'json'")
    if scenario_path.is_dir():
        result = asyncio.run(run_suite(scenario_path))
    else:
        scenario = Scenario.from_yaml(str(scenario_path))
        contracts = load_contracts(scenario_path.parent / "tools.json")
        result = asyncio.run(Runner(contracts).run(scenario))
    typer.echo(render_json(result) if report == "json" else render_console(result))
    if isinstance(result, SuiteResult) and result.regressions:
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the installed ToolFuzz version."""
    from . import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
