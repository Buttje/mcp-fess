"""Tests for logging_utils module."""

import logging
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from mcp_fess.logging_utils import ElapsedTimeFormatter, setup_logging


class TestElapsedTimeFormatter:
    """Test ElapsedTimeFormatter class."""

    def test_format_with_elapsed_time(self):
        """Test formatting with elapsed time."""
        start_time = datetime.now() - timedelta(hours=2, minutes=30, seconds=45)
        formatter = ElapsedTimeFormatter(
            start_time, fmt="[%(elapsed_time)s] %(levelname)s: %(message)s"
        )

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        assert "[" in formatted
        assert "] INFO: Test message" in formatted
        assert hasattr(record, "elapsed_time")
        # Check format is HH:MM:SS
        parts = record.elapsed_time.split(":")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_format_elapsed_time_format(self):
        """Test elapsed time format is correct."""
        start_time = datetime.now() - timedelta(seconds=3665)  # 1 hour, 1 minute, 5 seconds
        formatter = ElapsedTimeFormatter(start_time)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )

        formatter.format(record)
        # Should be around 01:01:05
        hours, minutes, seconds = record.elapsed_time.split(":")
        assert hours == "01"
        assert minutes == "01"
        # Seconds might be 04 or 05 due to timing
        assert seconds in ["04", "05", "06"]


class TestSetupLogging:
    """Test setup_logging function."""

    def test_setup_logging_debug_mode(self):
        """Test setup logging in debug mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, debug_file_handle = setup_logging(log_dir, debug=True)

            assert logger.name == "mcp_fess"
            assert logger.level == logging.DEBUG
            assert debug_file_handle is not None

            # Check that debug log file was created
            log_files = list(log_dir.glob("*_server.log"))
            assert len(log_files) == 1

            # Verify logger has handlers
            assert len(logger.handlers) == 2  # File handler + console handler

            # Test that log messages work
            logger.debug("Debug message")
            debug_file_handle.flush()

            # Clean up
            debug_file_handle.close()
            logger.handlers.clear()

    def test_setup_logging_normal_mode(self):
        """Test setup logging in normal mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, debug_file_handle = setup_logging(log_dir, debug=False)

            assert logger.name == "mcp_fess"
            assert logger.level == logging.INFO
            assert debug_file_handle is None

            # Check that stable log file was created
            stable_log = log_dir / "server.log"
            assert stable_log.exists()

            # Verify logger has handlers
            assert len(logger.handlers) == 2  # File handler + console handler

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_level_error(self):
        """Test setup logging with error level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False, level="error")

            assert logger.level == logging.ERROR

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_level_warn(self):
        """Test setup logging with warn level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False, level="warn")

            assert logger.level == logging.WARN

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_level_debug(self):
        """Test setup logging with debug level (non-debug mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False, level="debug")

            assert logger.level == logging.DEBUG

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_level_invalid_defaults_to_info(self):
        """Test setup logging with invalid level defaults to INFO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False, level="invalid")

            assert logger.level == logging.INFO

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_clears_existing_handlers(self):
        """Test that setup_logging clears existing handlers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Get logger and add a handler
            logger = logging.getLogger("mcp_fess")
            logger.addHandler(logging.StreamHandler())
            initial_handler_count = len(logger.handlers)
            assert initial_handler_count > 0

            # Setup logging should clear handlers
            logger, _ = setup_logging(log_dir, debug=False)

            # Should have exactly 2 handlers (file + console)
            assert len(logger.handlers) == 2

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_console_handler_stderr(self):
        """Test that console handler outputs to stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False)

            # Find console handler
            console_handler = None
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stderr:
                    console_handler = handler
                    break

            assert console_handler is not None
            assert console_handler.level == logging.WARNING

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_debug_file_timestamp_format(self):
        """Test that debug log file has correct timestamp format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            with patch("mcp_fess.logging_utils.datetime") as mock_datetime:
                mock_now = datetime(2024, 1, 15, 14, 30, 45)
                mock_datetime.now.return_value = mock_now

                logger, debug_file_handle = setup_logging(log_dir, debug=True)

                # Check filename
                expected_filename = "20240115_143045_server.log"
                log_file = log_dir / expected_filename
                assert log_file.exists()

                # Clean up
                debug_file_handle.close()
                logger.handlers.clear()

    def test_setup_logging_debug_formatter_has_elapsed_time(self):
        """Test that debug mode uses ElapsedTimeFormatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, debug_file_handle = setup_logging(log_dir, debug=True)

            # Find file handler
            file_handler = None
            for handler in logger.handlers:
                if hasattr(handler, "stream") and handler.stream == debug_file_handle:
                    file_handler = handler
                    break

            assert file_handler is not None
            assert isinstance(file_handler.formatter, ElapsedTimeFormatter)

            # Clean up
            debug_file_handle.close()
            logger.handlers.clear()

    def test_setup_logging_normal_mode_formatter(self):
        """Test that normal mode uses standard formatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False)

            # Find file handler
            file_handler = None
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    file_handler = handler
                    break

            assert file_handler is not None
            assert not isinstance(file_handler.formatter, ElapsedTimeFormatter)
            assert isinstance(file_handler.formatter, logging.Formatter)

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_writes_to_file(self):
        """Test that logging actually writes to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, _ = setup_logging(log_dir, debug=False, level="info")

            test_message = "Test log message"
            logger.info(test_message)

            # Force flush
            for handler in logger.handlers:
                handler.flush()

            # Read log file
            log_file = log_dir / "server.log"
            content = log_file.read_text()
            assert test_message in content
            assert "INFO" in content

            # Clean up
            logger.handlers.clear()

    def test_setup_logging_debug_writes_to_file(self):
        """Test that debug logging writes to timestamped file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            logger, debug_file_handle = setup_logging(log_dir, debug=True)

            test_message = "Debug test message"
            logger.debug(test_message)

            # Force flush
            debug_file_handle.flush()

            # Read log file
            log_files = list(log_dir.glob("*_server.log"))
            assert len(log_files) == 1
            content = log_files[0].read_text()
            assert test_message in content
            assert "DEBUG" in content

            # Clean up
            debug_file_handle.close()
            logger.handlers.clear()
