"""Power source detection for the "only on mains power" schedule option."""

from __future__ import annotations

import os


def on_battery() -> bool:
    """True only when Windows reports the PC is running on battery; unknown means plugged in."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
            ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
            ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD),
        ]

    status = SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return False
    return status.ACLineStatus == 0
