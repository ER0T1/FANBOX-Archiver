"""Cross-process ownership of one archive.

The desktop app (via ``serve``) holds the lock for its whole lifetime, and the
background ``schedule-run`` holds it while it backs up, so two processes never
write the same archive. The OS drops the lock if the holder crashes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

LOCK_NAME = ".fanbox-archiver.lock"
# Lock a byte far past the end of the (empty) file so copying the archive, which
# reads the file's real contents, is never blocked by the lock itself.
_LOCK_OFFSET = 0x7FFF_FFF0


class ArchiveLock:
    def __init__(self, root: Path) -> None:
        self.path = Path(root) / LOCK_NAME
        self._handle: BinaryIO | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def try_acquire(self) -> bool:
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(_LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(_LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            handle.close()

    def held_elsewhere(self) -> bool:
        """True when another process (or another lock object) owns the archive."""
        if self._handle is not None:
            return False
        if self.try_acquire():
            self.release()
            return False
        return True
