"""Deterministic image storage for snippet engine."""

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")


def compute_doc_hash(file_path: Path) -> str:
    """Compute a short hash of a file path for deterministic naming."""
    return hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:12]


def save_image(
    image_data: bytes,
    images_root: Path,
    doc_hash: str,
    page: int,
    index: int,
    prefer_jpeg: bool = False,
) -> Path:
    """Save an image to images_root with a deterministic filename.

    Args:
        image_data: Raw image bytes.
        images_root: Directory to save images into.
        doc_hash: Short hash of the source document.
        page: Page number (1-based).
        index: Image index on the page (0-based).
        prefer_jpeg: Use .jpg extension if True, else .png.

    Returns:
        Absolute Path of the saved image.
    """
    img_hash = hashlib.sha256(image_data).hexdigest()[:8]
    ext = ".jpg" if prefer_jpeg else ".png"
    filename = f"{doc_hash}_p{page}_i{index}_{img_hash}{ext}"
    out_path = images_root / filename
    out_path.write_bytes(image_data)
    return out_path
