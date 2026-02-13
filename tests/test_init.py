"""Tests for the MCP Fess package."""

import mcp_fess
from fastmcp import FastMCP


def test_version():
    """Test that the package version is defined."""
    assert hasattr(mcp_fess, "__version__")
    assert isinstance(mcp_fess.__version__, str)
    assert mcp_fess.__version__ == "0.1.0"


def test_mcp_instance_exported():
    """Test that the top-level mcp instance is exported."""
    assert hasattr(mcp_fess, "mcp")
    assert isinstance(mcp_fess.mcp, FastMCP)
    # Verify the name follows the expected pattern
    assert mcp_fess.mcp.name.startswith("mcp-fess-")

