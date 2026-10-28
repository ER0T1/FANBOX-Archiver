"""Application use cases shared by CLI and web interfaces."""

from .backup import BackupOutcome, BackupRequest, BackupUseCase
from .events import BackupCancelled, BackupEvent, CancellationToken, EventSink, NullEventSink
from .jobs import BackupJobManager

__all__ = [
    "BackupCancelled", "BackupEvent", "BackupOutcome", "BackupRequest",
    "BackupUseCase", "BackupJobManager", "CancellationToken", "EventSink", "NullEventSink",
]
