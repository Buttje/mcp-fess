"""Dispatch document conversion to format-specific extractors."""

import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")


def convert_document(
    file_path: Path,
    images_root: Path,
    doc_hash: str,
) -> tuple[list[tuple[int, str]], list[Path]]:
    """Convert a document to (page, line) tuples and extract images.

    Args:
        file_path: Path to the source document.
        images_root: Directory to save extracted images.
        doc_hash: Short hash of the source document for unique naming.

    Returns:
        Tuple of:
        - List of (page_number, line_text) tuples.
        - List of extracted image file Paths.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        from .pdf_extract import extract_pdf

        return extract_pdf(file_path, images_root, doc_hash)

    if suffix == ".docx":
        from .docx_extract import extract_docx

        return extract_docx(file_path, images_root, doc_hash)

    # Default: plain text
    from .text_extract import extract_text_lines

    text_lines = extract_text_lines(file_path)
    page_lines = [(1, line) for line in text_lines]
    return page_lines, []
