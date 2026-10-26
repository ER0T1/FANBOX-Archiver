from __future__ import annotations

import logging
import re
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from .config import AppConfig


LOGGER_NAME = "fanbox_archiver"


class SensitiveDataFilter(logging.Filter):
    """Last-line defence against credentials entering local log files."""

    _patterns = (
        re.compile(r"(?i)(cookie|authorization)\s*[:=]\s*[^\r\n]+"),
        re.compile(r"(?i)(token|access_token|refresh_token|key)=([^&\s]+)"),
        re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._~+/-]+=*"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(config: AppConfig) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, config.logging.level))
    logger.propagate = False
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    if config.logging.write_to_file:
        log_dir = (config.storage.output_dir / "logs").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(
            log_dir / "fanbox-archiver.log", when="midnight",
            backupCount=config.logging.keep_days, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
