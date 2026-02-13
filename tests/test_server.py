"""Tests for the server module."""

from mcp_fess.server import main


def test_main_exists():
    """Test that the main function exists."""
    assert callable(main)
