"""JSON serialization for run results."""

import json

from ..core.models import RunResult, SuiteResult


def render(result: RunResult | SuiteResult) -> str:
    return json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
