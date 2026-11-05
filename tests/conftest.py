import pytest

from fanbox_archiver import cli, timestamps, windows_task


@pytest.fixture(autouse=True)
def traditional_chinese_system_language(monkeypatch):
    """Development and test baseline: the system language is zh-TW on every machine.

    ``auto`` follows the operating system (an English CI runner would otherwise get the English
    catalog); tests that need another system language patch these again.
    """
    for module in (cli, windows_task):
        monkeypatch.setattr(module, "system_locales", lambda: ["zh-TW"])


@pytest.fixture(autouse=True)
def taipei_development_timezone(monkeypatch):
    """Development and test baseline: the "system" timezone is Asia/Taipei on every machine."""
    monkeypatch.setattr(timestamps, "_system_timezone_name", lambda: timestamps.DEVELOPMENT_TIMEZONE)
    timestamps.set_display_timezone(timestamps.SYSTEM)
    yield
    timestamps.set_display_timezone(timestamps.SYSTEM)
