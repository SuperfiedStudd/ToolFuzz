"""Structured trace collection."""

from typing import Any

from .models import TraceEvent


class Trace:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(self, event_type: str, **metadata: Any) -> TraceEvent:
        event = TraceEvent(event_type=event_type, metadata=metadata)
        self.events.append(event)
        return event

    def count(self, event_type: str) -> int:
        return sum(event.event_type == event_type for event in self.events)

    def metadata_for(self, event_type: str) -> list[dict[str, Any]]:
        return [
            event.metadata for event in self.events if event.event_type == event_type
        ]
