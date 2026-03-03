"""DOCX text and image extraction using python-docx."""

import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")


def extract_docx(
    file_path: Path,
    images_root: Path,
    doc_hash: str,
) -> tuple[list[tuple[int, str]], list[Path]]:
    """Extract text lines and images from a DOCX file.

    Args:
        file_path: Path to the DOCX file.
        images_root: Directory to save images into.
        doc_hash: Short hash of the source document.

    Returns:
        Tuple of:
        - List of (page_number, line_text) tuples (page always 1 for DOCX).
        - List of extracted image Paths.
    """
    try:
        import docx
    except ImportError:
        logger.warning("python-docx not available; DOCX extraction skipped for %s", file_path)
        return [], []

    from .image_store import save_image

    lines: list[tuple[int, str]] = []
    images: list[Path] = []

    try:
        document = docx.Document(str(file_path))
    except Exception as e:
        logger.warning("Failed to open DOCX %s: %s", file_path, e)
        return [], []

    # Extract paragraphs (all on "page 1" since DOCX has no real page boundaries)
    for para in document.paragraphs:
        text = para.text
        for line in text.splitlines():
            lines.append((1, line))

    # Extract images from the document's part relationships
    img_idx = 0
    try:
        doc_part = document.part
        for rel in doc_part.rels.values():
            if "image" in rel.reltype:
                try:
                    image_blob = rel.target_part.blob
                    content_type = rel.target_part.content_type.lower()
                    prefer_jpeg = "jpeg" in content_type or "jpg" in content_type
                    img_path = save_image(
                        image_blob,
                        images_root,
                        doc_hash,
                        1,
                        img_idx,
                        prefer_jpeg=prefer_jpeg,
                    )
                    images.append(img_path)
                    lines.append((1, f"<IMAGE: {img_path}>"))
                    img_idx += 1
                except Exception as e:
                    logger.warning("Failed to extract image from DOCX %s: %s", file_path, e)
    except Exception as e:
        logger.warning("Failed to extract images from DOCX %s: %s", file_path, e)

    return lines, images
