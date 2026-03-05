"""Recursively scan a directory for supported document files."""

import fnmatch
import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".odt", ".txt", ".md", ".rst", ".csv", ".html", ".htm"}


def scan_directory(
    input_dir: Path,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[Path]:
    """Recursively scan input_dir and return matching file paths.

    Args:
        input_dir: Directory to scan.
        include_globs: Glob patterns to include (default: supported extensions).
        exclude_globs: Glob patterns to exclude.

    Returns:
        List of matching file Paths.
    """
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist or is not a directory: {input_dir}")

    results: list[Path] = []
    for path in sorted(input_dir.rglob("*")):
        if path.is_dir():
            continue

        rel = str(path.relative_to(input_dir))

        # Apply exclude filters
        if exclude_globs and any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs):
            logger.debug("Excluded: %s", path)
            continue

        # Apply include filters
        if include_globs:
            if not any(fnmatch.fnmatch(rel, pat) for pat in include_globs):
                logger.debug("Not matching include: %s", path)
                continue
        else:
            # Default: supported extensions only
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                logger.debug("Unsupported extension: %s", path)
                continue

        results.append(path)

    return results
