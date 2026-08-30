import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from toolfuzz.agents.anthropic import AnthropicAgent
from toolfuzz.agents.base import (
    MaxAgentTurnsError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
)
from toolfuzz.agents.gemini import GeminiAgent
from toolfuzz.agents.normalization import (
    normalize_anthropic_tool_calls,
    normalize_gemini_tool_calls,
    normalize_openai_tool_calls,
    to_anthropic_tool_result,
    to_anthropic_tools,
    to_gemini_tool_result,
    to_gemini_tools,
    to_openai_tool_result,
    to_openai_tools,
)
from toolfuzz.agents.openai import OpenAIAgent
from toolfuzz.core.models import ToolContract, ToolResult
from toolfuzz.core.trace import Trace

ROOT = Path(__file__).parents[1]


def load_contracts() -> list[ToolContract]:
    with (ROOT / "examples/refund_agent/tools.json").open() as tools_file:
        return [ToolContract.model_validate(item) for item in json.load(tools_file)]


def success_result() -> ToolResult:
    return ToolResult(success=True, output={"ok": True})


def test_contracts_convert_to_provider_declarations_and_results() -> None:
    contracts = load_contracts()

    gemini = to_gemini_tools(contracts)
    openai = to_openai_tools(contracts)
    anthropic = to_anthropic_tools(contracts)

    assert len(gemini[0]["function_declarations"]) == 3
    assert openai[0]["function"]["parameters"]["required"]
    assert anthropic[0]["input_schema"]["required"]
    call = normalize_openai_tool_calls(
        SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    id="openai-call",
                    function=SimpleNamespace(
                        name="get_order",
                        arguments='{"order_id":"ORD-104"}',
                    ),
                )
            ]
        )
    )[0]
    assert to_openai_tool_result(call, success_result())["tool_call_id"] == "openai-call"
    assert to_anthropic_tool_result(call, success_result())["is_error"] is False
    assert to_gemini_tool_result(call, success_result())["function_response"]["name"] == "get_order"


def test_provider_tool_call_normalization() -> None:
    assert normalize_gemini_tool_calls(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"function_call": {"name": "get_order", "args": {"order_id": "ORD-104"}}}
                        ]
                    }
                }
            ]
        }
    )[0].call.tool_name == "get_order"
    assert normalize_anthropic_tool_calls(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "anthropic-call",
                    "name": "get_order",
                    "input": {"order_id": "ORD-104"},
                }
            ]
        }
    )[0].provider_call_id == "anthropic-call"


class FakeGeminiModels:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def generate_content(self, **request):
        self.requests.append(request)
        return next(self.responses)


class FakeGeminiClient:
    def __init__(self, responses):
        self.aio = SimpleNamespace(models=FakeGeminiModels(responses))


@pytest.mark.asyncio
async def test_gemini_runs_multiple_tool_turns_and_finishes() -> None:
    client = FakeGeminiClient(
        [
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "function_call": {
                                        "name": "get_order",
                                        "args": {"order_id": "ORD-104"},
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
            {"text": "Refund completed safely."},
        ]
    )
    trace = Trace()
    agent = GeminiAgent(load_contracts(), client=client, trace=trace)
    calls = []

    async def call_tool(name, arguments):
        calls.append((name, arguments))
        return success_result()

    await agent.run("Refund ORD-104.", call_tool)

    assert calls == [("get_order", {"order_id": "ORD-104"})]
    assert agent.final_response == "Refund completed safely."
    assert len(client.aio.models.requests) == 2
    assert trace.count("provider_tool_request") == 1
    assert trace.count("provider_complete") == 1


@pytest.mark.asyncio
async def test_openai_and_anthropic_complete_after_tool_turn() -> None:
    openai_messages = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                id="oai-call",
                                function=SimpleNamespace(
                                    name="get_order",
                                    arguments='{"order_id":"ORD-104"}',
                                ),
                            )
                        ],
                        content=None,
                    )
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(tool_calls=[], content="done"),
                )
            ]
        ),
    ]

    class OpenAICompletions:
        def __init__(self):
            self.responses = iter(openai_messages)

        async def create(self, **kwargs):
            return next(self.responses)

    openai_agent = OpenAIAgent(
        load_contracts(),
        client=SimpleNamespace(
            chat=SimpleNamespace(completions=OpenAICompletions())
        ),
    )

    anthropic_responses = [
        SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="anthropic-call",
                    name="get_order",
                    input={"order_id": "ORD-104"},
                )
            ]
        ),
        SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
        ),
    ]

    class AnthropicMessages:
        def __init__(self):
            self.responses = iter(anthropic_responses)

        async def create(self, **kwargs):
            return next(self.responses)

    anthropic_agent = AnthropicAgent(
        load_contracts(),
        client=SimpleNamespace(messages=AnthropicMessages()),
    )

    async def call_tool(name, arguments):
        assert name == "get_order"
        assert arguments["order_id"] == "ORD-104"
        return success_result()

    await openai_agent.run("Read order.", call_tool)
    await anthropic_agent.run("Read order.", call_tool)
    assert openai_agent.final_response == "done"
    assert anthropic_agent.final_response == "done"


@pytest.mark.asyncio
async def test_gemini_max_turn_cutoff() -> None:
    repeating_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"function_call": {"name": "get_order", "args": {"order_id": "ORD-104"}}}
                    ]
                }
            }
        ]
    }
    agent = GeminiAgent(
        load_contracts(),
        client=FakeGeminiClient([repeating_response, repeating_response]),
        max_agent_turns=2,
    )

    async def call_tool(name, arguments):
        del name, arguments
        return success_result()

    with pytest.raises(MaxAgentTurnsError):
        await agent.run("Loop.", call_tool)


@pytest.mark.parametrize(
    ("agent_type", "env_name"),
    [
        (GeminiAgent, "GEMINI_API_KEY"),
        (OpenAIAgent, "OPENAI_API_KEY"),
        (AnthropicAgent, "ANTHROPIC_API_KEY"),
    ],
)
def test_missing_provider_api_key_is_configuration_error(
    agent_type,
    env_name,
    monkeypatch,
) -> None:
    monkeypatch.delenv(env_name, raising=False)
    with pytest.raises(ProviderConfigurationError):
        agent_type(load_contracts())


def test_provider_errors_are_normalized_and_trace_values_are_redacted() -> None:
    class UnauthorizedError(Exception):
        status_code = 401

    from toolfuzz.agents.base import normalize_provider_exception

    assert isinstance(
        normalize_provider_exception(UnauthorizedError("bad key")),
        ProviderAuthenticationError,
    )
    rate_error = Exception("rate limited")
    rate_error.status_code = 429
    assert isinstance(normalize_provider_exception(rate_error), ProviderRateLimitError)

    trace = Trace()
    trace.record("provider_error", api_key="secret-value", authorization="Bearer secret")
    assert trace.events[0].metadata == {
        "api_key": "[REDACTED]",
        "authorization": "[REDACTED]",
    }
