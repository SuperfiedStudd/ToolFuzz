from toolfuzz.contracts.validator import validate_input, validate_output
from toolfuzz.core.models import ToolContract


def test_contract_validator_accepts_valid_values() -> None:
    contract = ToolContract(
        name="lookup",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        output_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    )

    assert validate_input(contract, {"order_id": "ORD-104"}) == []
    assert validate_output(contract, {"status": "delivered"}) == []


def test_contract_validator_reports_input_and_output_violations() -> None:
    contract = ToolContract(
        name="lookup",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        output_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    )

    assert validate_input(contract, {}) == ["<root>: 'order_id' is a required property"]
    assert validate_output(contract, {"status": 503}) == [
        "status: 503 is not of type 'string'"
    ]
