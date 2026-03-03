"""Write Markdown snippet files with provenance markers."""

import logging
from io import TextIOWrapper
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")

MAX_BYTES = 10 * 1024 * 1024  # 10 MiB


def _make_header(original_path: Path, start_page: int, start_line: int) -> str:
    """Build the provenance header block for a snippet file."""
    return (
        f"{original_path}\n"
        f"p{start_page} l{start_line}\n"
        "{{p<number>:= Page number; l<number>:= Line number}}\n"
    )


def write_snippets(
    original_path: Path,
    page_lines: list[tuple[int, str]],
    snippets_root: Path,
    doc_hash: str,
    max_bytes: int = MAX_BYTES,
) -> list[Path]:
    """Write Markdown snippet files for a document.

    Each output file is strictly < max_bytes in UTF-8 bytes.
    Files are named:
        {safe_basename}.{doc_hash}.part{NNNN}.md

    Args:
        original_path: Absolute path of the source document.
        page_lines: List of (page_number, line_text) tuples.
        snippets_root: Directory to write .md files into.
        doc_hash: Short hash of the document for file naming.
        max_bytes: Maximum bytes per .md file (default 10 MiB).

    Returns:
        List of Paths to the created .md files.
    """
    safe_basename = _safe_name(original_path.name)
    output_paths: list[Path] = []

    part_num = 1
    current_fh: TextIOWrapper | None = None
    current_bytes = 0
    line_num = 1  # global line counter (continuous across parts)

    def _open_new_part(start_page: int, start_ln: int) -> tuple[Path, TextIOWrapper, int]:
        nonlocal part_num
        fname = f"{safe_basename}.{doc_hash}.part{part_num:04d}.md"
        fpath = snippets_root / fname
        fh = fpath.open("w", encoding="utf-8")
        header = _make_header(original_path, start_page, start_ln)
        fh.write(header)
        part_num += 1
        output_paths.append(fpath)
        return fpath, fh, len(header.encode("utf-8"))

    if not page_lines:
        # Write an empty snippet with just the header
        _, fh, _ = _open_new_part(1, 1)
        fh.close()
        return output_paths

    first_page = page_lines[0][0]
    _current_file, current_fh, current_bytes = _open_new_part(first_page, 1)

    for page, text in page_lines:
        content_line = f"p{page} l{line_num}: {text}\n"
        line_bytes = len(content_line.encode("utf-8"))

        if current_bytes + line_bytes >= max_bytes:
            # Close current part, open new one
            current_fh.close()
            _current_file, current_fh, current_bytes = _open_new_part(page, line_num)

        current_fh.write(content_line)
        current_bytes += line_bytes
        line_num += 1

    if current_fh:
        current_fh.close()

    return output_paths


def _safe_name(name: str) -> str:
    """Convert a filename to a safe basename for use in output filenames."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return safe[:80]  # keep reasonable length
