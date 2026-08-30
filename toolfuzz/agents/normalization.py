"""Provider-neutral tool-call and tool-result normalization."""

import json
from dataclasses import dataclass
from typing import Any, Iterable

from ..core.models import ToolCall, ToolContract, ToolResult
from .base import ProviderResponseError


@dataclass(frozen=True)
class NormalizedToolCall:
    call: ToolCall
    provider_call_id: str | None = None


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def as_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: as_jsonable(item) for key, item in value.items()}
    return value


def conservative_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Keep the portable JSON Schema subset supported by all providers."""
    allowed = {"type", "properties", "required", "items", "enum", "description"}
    normalized: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in allowed:
            continue
        if key == "properties":
            normalized[key] = {
                name: conservative_schema(property_schema)
                for name, property_schema in value.items()
            }
        elif key == "items" and isinstance(value, dict):
            normalized[key] = conservative_schema(value)
        else:
            normalized[key] = value
    return normalized


def _function_declaration(contract: ToolContract) -> dict[str, Any]:
    return {
        "name": contract.name,
        "description": contract.description,
        "parameters": conservative_schema(contract.input_schema),
    }


def to_gemini_tools(contracts: Iterable[ToolContract]) -> list[dict[str, Any]]:
    return [
        {
            "function_declarations": [
                _function_declaration(contract) for contract in contracts
            ]
        }
    ]


def to_openai_tools(contracts: Iterable[ToolContract]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": _function_declaration(contract),
        }
        for contract in contracts
    ]


def to_anthropic_tools(contracts: Iterable[ToolContract]) -> list[dict[str, Any]]:
    return [
        {
            "name": contract.name,
            "description": contract.description,
            "input_schema": conservative_schema(contract.input_schema),
        }
        for contract in contracts
    ]


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ProviderResponseError(
                "provider returned invalid tool arguments"
            ) from error
    if not isinstance(value, dict):
        raise ProviderResponseError("provider returned non-object tool arguments")
    return value


def normalize_openai_tool_calls(message: Any) -> list[NormalizedToolCall]:
    normalized = []
    for tool_call in _field(message, "tool_calls", []) or []:
        function = _field(tool_call, "function", {})
        normalized.append(
            NormalizedToolCall(
                ToolCall(
                    tool_name=_field(function, "name", ""),
                    arguments=_arguments(_field(function, "arguments", {})),
                ),
                provider_call_id=_field(tool_call, "id"),
            )
        )
    return normalized


def normalize_anthropic_tool_calls(response: Any) -> list[NormalizedToolCall]:
    normalized = []
    for block in _field(response, "content", []) or []:
        if _field(block, "type") != "tool_use":
            continue
        normalized.append(
            NormalizedToolCall(
                ToolCall(
                    tool_name=_field(block, "name", ""),
                    arguments=_arguments(_field(block, "input", {})),
                ),
                provider_call_id=_field(block, "id"),
            )
        )
    return normalized


def normalize_gemini_tool_calls(response: Any) -> list[NormalizedToolCall]:
    normalized = []
    for candidate in _field(response, "candidates", []) or []:
        content = _field(candidate, "content", {})
        for part in _field(content, "parts", []) or []:
            function_call = _field(part, "function_call")
            if function_call is None:
                continue
            normalized.append(
                NormalizedToolCall(
                    ToolCall(
                        tool_name=_field(function_call, "name", ""),
                        arguments=_arguments(_field(function_call, "args", {})),
                    )
                )
            )
    return normalized


def tool_result_payload(result: ToolResult) -> dict[str, Any]:
    if result.success:
        return {"output": result.output}
    return {
        "error": {
            "type": result.error_type,
            "message": result.error_message,
        }
    }


def to_openai_tool_result(
    call: NormalizedToolCall, result: ToolResult
) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.provider_call_id,
        "content": json.dumps(tool_result_payload(result)),
    }


def to_anthropic_tool_result(
    call: NormalizedToolCall, result: ToolResult
) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": call.provider_call_id,
        "content": json.dumps(tool_result_payload(result)),
        "is_error": not result.success,
    }


def to_gemini_tool_result(
    call: NormalizedToolCall, result: ToolResult
) -> dict[str, Any]:
    return {
        "function_response": {
            "name": call.call.tool_name,
            "response": tool_result_payload(result),
        }
    }


def openai_final_text(message: Any) -> str:
    return str(_field(message, "content", "") or "")


def anthropic_final_text(response: Any) -> str:
    return "\n".join(
        str(_field(block, "text", ""))
        for block in (_field(response, "content", []) or [])
        if _field(block, "type") == "text"
    ).strip()


def gemini_final_text(response: Any) -> str:
    return str(_field(response, "text", "") or "")
