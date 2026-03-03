"""Plain text / Markdown / other text format extractor."""

import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")


def extract_text_lines(file_path: Path) -> list[str]:
    """Extract lines from a plain text file.

    Args:
        file_path: Path to the text file.

    Returns:
        List of text lines (without newlines).
    """
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning("Failed to read %s: %s", file_path, e)
        return []
    return text.splitlines()
