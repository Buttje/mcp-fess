"""PDF text and image extraction using PyMuPDF."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("mcp_fess.snippet_engine")


def extract_pdf(
    file_path: Path,
    images_root: Path,
    doc_hash: str,
) -> tuple[list[tuple[int, str]], list[Path]]:
    """Extract text lines and images from a PDF.

    Args:
        file_path: Path to the PDF file.
        images_root: Directory to save images into.
        doc_hash: Short hash of the source document.

    Returns:
        Tuple of:
        - List of (page_number, line_text) tuples (page is 1-based).
        - List of extracted image Paths.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not available; PDF extraction skipped for %s", file_path)
        return [], []

    from .image_store import save_image

    lines: list[tuple[int, str]] = []
    images: list[Path] = []

    try:
        doc = fitz.open(str(file_path))
    except Exception as e:
        logger.warning("Failed to open PDF %s: %s", file_path, e)
        return [], []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_1based = page_num + 1

            # Extract text lines
            text = page.get_text("text")
            for line in text.splitlines():
                lines.append((page_1based, line))

            # Extract images
            img_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(img_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image.get("ext", "png").lower()
                    prefer_jpeg = image_ext in ("jpg", "jpeg", "jfif")
                    img_path = save_image(
                        image_bytes,
                        images_root,
                        doc_hash,
                        page_1based,
                        img_idx,
                        prefer_jpeg=prefer_jpeg,
                    )
                    images.append(img_path)
                    # Insert image placeholder into lines
                    lines.append((page_1based, f"<IMAGE: {img_path}>"))
                except Exception as e:
                    logger.warning(
                        "Failed to extract image xref=%d from %s: %s", xref, file_path, e
                    )
    finally:
        doc.close()

    return lines, images
