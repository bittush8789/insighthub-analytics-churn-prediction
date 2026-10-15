"""Structured application logging configuration."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from src.config.settings import get_settings


class SensitiveDataFilter(logging.Filter):
    """Filter that intercepts and masks potential secret patterns from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # Redact common credential patterns if accidentally passed
        if "AIza" in msg:  # Google API key prefix
            record.msg = "[REDACTED_API_KEY]"
        if "password" in msg.lower() and "=" in msg:
            record.msg = "[REDACTED_CREDENTIALS]"
        return True


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[Path] = None,
    log_filename: str = "app.log",
) -> logging.Logger:
    """Configure root logger with console and rotating file handlers.

    Args:
        log_level: Desired log level string (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory where log files are stored.
        log_filename: Target log file name.

    Returns:
        Configured logger instance.
    """
    settings = get_settings()
    level_name = log_level or settings.LOG_LEVEL
    level = getattr(logging, level_name.upper(), logging.INFO)

    target_dir = log_dir or settings.LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    log_filepath = target_dir / log_filename

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers if already configured
    if not root_logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(console_handler)

        # Rotating File Handler (10MB max, 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_filepath),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)

    # Suppress verbose noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger("ecommerce_analytics")
    logger.info("Structured logging initialized at %s level -> %s", level_name, log_filepath)
    return logger
