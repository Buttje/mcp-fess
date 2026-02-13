"""Tests for the MCP Fess package."""

import mcp_fess


def test_version():
    """Test that the package version is defined."""
    assert hasattr(mcp_fess, "__version__")
    assert isinstance(mcp_fess.__version__, str)
    assert mcp_fess.__version__ == "0.1.0"
