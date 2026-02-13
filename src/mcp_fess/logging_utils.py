"""Logging utilities for MCP-Fess server."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO


class ElapsedTimeFormatter(logging.Formatter):
    """Formatter that adds elapsed time since start."""

    def __init__(self, start_time: datetime, fmt: str | None = None) -> None:
        super().__init__(fmt)
        self.start_time = start_time

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with elapsed time."""
        elapsed = datetime.now() - self.start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        record.elapsed_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return super().format(record)


def setup_logging(
    log_dir: Path, debug: bool = False, level: str = "info"
) -> tuple[logging.Logger, TextIO | None]:
    """
    Set up logging for the server.

    Args:
        log_dir: Directory for log files
        debug: Enable debug logging with elapsed time
        level: Default logging level (error/warn/info/debug)

    Returns:
        Tuple of (logger, optional debug file handle)
    """
    logger = logging.getLogger("mcp_fess")
    logger.setLevel(logging.DEBUG if debug else getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    debug_file_handle = None

    if debug:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_log_path = log_dir / f"{timestamp}_server.log"
        debug_file_handle = debug_log_path.open("w", encoding="utf-8")

        handler = logging.StreamHandler(debug_file_handle)
        formatter = ElapsedTimeFormatter(
            datetime.now(), fmt="[%(elapsed_time)s] %(levelname)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        stable_log_path = log_dir / "server.log"
        handler = logging.FileHandler(stable_log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger, debug_file_handle
