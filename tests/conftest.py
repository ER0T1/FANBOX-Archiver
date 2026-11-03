import pytest

from fanbox_archiver import timestamps


@pytest.fixture(autouse=True)
def taipei_development_timezone(monkeypatch):
    """Development and test baseline: the "system" timezone is Asia/Taipei on every machine."""
    monkeypatch.setattr(timestamps, "_system_timezone_name", lambda: timestamps.DEVELOPMENT_TIMEZONE)
    timestamps.set_display_timezone(timestamps.SYSTEM)
    yield
    timestamps.set_display_timezone(timestamps.SYSTEM)
