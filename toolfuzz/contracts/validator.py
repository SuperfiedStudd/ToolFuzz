"""JSON Schema validation for tool inputs and outputs."""

from typing import Any

from jsonschema import Draft202012Validator

from ..core.models import ToolContract


def validate_against_schema(
    value: Any,
    schema: dict[str, Any],
) -> list[str]:
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    return [
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors
    ]


def validate_input(contract: ToolContract, arguments: dict[str, Any]) -> list[str]:
    return validate_against_schema(arguments, contract.input_schema)


def validate_output(contract: ToolContract, output: Any) -> list[str]:
    return validate_against_schema(output, contract.output_schema)
