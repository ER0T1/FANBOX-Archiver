"""Application use cases shared by CLI and web interfaces."""

from .backup import BackupOutcome, BackupRequest, BackupUseCase
from .auth import AuthStatus, AuthenticationJobManager, AuthenticationService
from .events import BackupCancelled, BackupEvent, CancellationToken, EventSink, NullEventSink
from .jobs import BackupJobManager
from .scheduler import BackupScheduler

__all__ = [
    "AuthStatus", "AuthenticationJobManager", "AuthenticationService",
    "BackupCancelled", "BackupEvent", "BackupOutcome", "BackupRequest",
    "BackupUseCase", "BackupJobManager", "BackupScheduler", "CancellationToken", "EventSink", "NullEventSink",
]
