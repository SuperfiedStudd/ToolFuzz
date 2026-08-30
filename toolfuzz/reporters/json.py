"""JSON serialization for run results."""

import json

from ..core.models import RunResult


def render(result: RunResult) -> str:
    return json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
