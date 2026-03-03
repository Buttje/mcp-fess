"""Split helpers — thin wrappers used by md_writer; exported for testing."""

# The actual splitting logic lives in md_writer.write_snippets.
# This module re-exports the MAX_BYTES constant and the write function
# so tests can import from a single predictable location.

from .md_writer import MAX_BYTES, write_snippets

__all__ = ["MAX_BYTES", "write_snippets"]
