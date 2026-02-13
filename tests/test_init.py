"""Tests for the MCP Fess package."""

from fastmcp import FastMCP

import mcp_fess


def test_version():
    """Test that the package version is defined."""
    assert hasattr(mcp_fess, "__version__")
    assert isinstance(mcp_fess.__version__, str)
    assert mcp_fess.__version__ == "0.1.0"


def test_mcp_instance_exported():
    """Test that the top-level mcp instance is exported."""
    assert hasattr(mcp_fess, "mcp")
    assert isinstance(mcp_fess.mcp, FastMCP)
    # Verify the name follows the expected pattern (before lifespan initialization)
    assert mcp_fess.mcp.name == "mcp-fess"
