"""MCP Server for Fess - A Model Context Protocol server implementation for Fess search."""

from .server import FessServer, main

__version__ = "0.1.0"

__all__ = ["FessServer", "__version__", "main"]
