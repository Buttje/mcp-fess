"""Top-level FastMCP instance for use with fastmcp run."""

from mcp_fess.config import load_config
from mcp_fess.server import FessServer

# Load configuration and create server instance
config = load_config()
_server = FessServer(config)

# Expose the FastMCP instance at the top level for fastmcp run
mcp = _server.mcp
