"""Command-line interface for ToolFuzz."""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from .core.models import Scenario, ToolContract
from .core.runner import Runner
from .reporters.console import render as render_console
from .reporters.json import render as render_json

app = typer.Typer(help="Adversarial reliability testing for tool-using AI agents.")


def load_contracts(path: Path) -> dict[str, ToolContract]:
    with path.open(encoding="utf-8") as tools_file:
        raw_contracts = json.load(tools_file)
    return {
        contract.name: contract
        for contract in (ToolContract.model_validate(item) for item in raw_contracts)
    }


@app.command()
def run(
    scenario_path: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, dir_okay=False),
    ],
    report: Annotated[
        str,
        typer.Option("--report", help="Report format: console or json."),
    ] = "console",
) -> None:
    """Run a YAML scenario against its sibling tools.json contracts."""
    if report not in {"console", "json"}:
        raise typer.BadParameter("must be 'console' or 'json'")
    scenario = Scenario.from_yaml(str(scenario_path))
    contracts = load_contracts(scenario_path.parent / "tools.json")
    result = asyncio.run(Runner(contracts).run(scenario))
    typer.echo(render_json(result) if report == "json" else render_console(result))


@app.command()
def version() -> None:
    """Print the installed ToolFuzz version."""
    from . import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
