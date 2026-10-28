from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Event
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class BackupEvent:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class EventSink(Protocol):
    def emit(self, event: BackupEvent) -> None: ...


class NullEventSink:
    def emit(self, event: BackupEvent) -> None:
        del event


class CollectingEventSink:
    def __init__(self) -> None:
        self.events: list[BackupEvent] = []

    def emit(self, event: BackupEvent) -> None:
        self.events.append(event)


class BackupCancelled(RuntimeError):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise BackupCancelled("備份已由使用者取消")
