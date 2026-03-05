"""ODT text and image extraction using odfpy."""

import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")


def extract_odt(
    file_path: Path,
    images_root: Path,
    doc_hash: str,
) -> tuple[list[tuple[int, str]], list[Path]]:
    """Extract text lines and images from an ODT file.

    Args:
        file_path: Path to the ODT file.
        images_root: Directory to save images into.
        doc_hash: Short hash of the source document.

    Returns:
        Tuple of:
        - List of (page_number, line_text) tuples (page always 1 for ODT).
        - List of extracted image Paths.
    """
    try:
        from odf.opendocument import load as odf_load
        from odf.text import P
    except ImportError:
        logger.warning("odfpy not available; ODT extraction skipped for %s", file_path)
        return [], []

    from .image_store import save_image

    lines: list[tuple[int, str]] = []
    images: list[Path] = []

    try:
        document = odf_load(str(file_path))
    except Exception as e:
        logger.warning("Failed to open ODT %s: %s", file_path, e)
        return [], []

    # Extract text paragraphs (all on "page 1" since ODT has no real page boundaries)
    try:
        for para in document.getElementsByType(P):
            text = str(para)
            for line in text.splitlines():
                lines.append((1, line))
    except Exception as e:
        logger.warning("Failed to extract text from ODT %s: %s", file_path, e)

    # Extract embedded images from the document's Pictures dict.
    # Each entry is (flag, image_bytes, media_type).
    img_idx = 0
    try:
        for _path, entry in document.Pictures.items():
            try:
                _flag, image_data, media_type = entry
                prefer_jpeg = "jpeg" in media_type.lower() or "jpg" in media_type.lower()
                img_path = save_image(
                    image_data,
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
                logger.warning("Failed to extract image from ODT %s: %s", file_path, e)
    except Exception as e:
        logger.warning("Failed to extract images from ODT %s: %s", file_path, e)

    return lines, images
