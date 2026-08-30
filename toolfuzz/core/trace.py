"""Structured trace collection with secret redaction."""

import os
from typing import Any

from .models import TraceEvent


_SECRET_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in _SECRET_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        for env_name in (
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            secret = os.getenv(env_name)
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {name: _redact(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


class Trace:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(self, event_type: str, **metadata: Any) -> TraceEvent:
        event = TraceEvent(event_type=event_type, metadata=_redact(metadata))
        self.events.append(event)
        return event

    def count(self, event_type: str) -> int:
        return sum(event.event_type == event_type for event in self.events)

    def metadata_for(self, event_type: str) -> list[dict[str, Any]]:
        return [
            event.metadata for event in self.events if event.event_type == event_type
        ]
