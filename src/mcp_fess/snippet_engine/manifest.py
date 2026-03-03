"""Write manifest.jsonl for snippet generation runs."""

import json
import logging
from pathlib import Path

logger = logging.getLogger("mcp_fess.snippet_engine")


def append_manifest_entry(
    manifest_path: Path,
    original_path: Path,
    doc_hash: str,
    snippet_parts: list[Path],
    images: list[Path],
    warnings: list[str] | None = None,
) -> None:
    """Append one entry to the JSONL manifest file.

    Args:
        manifest_path: Path to the manifest.jsonl file.
        original_path: Absolute path of the source document.
        doc_hash: Short hash of the document.
        snippet_parts: Paths to generated .md part files.
        images: Paths to extracted image files.
        warnings: Any warnings generated during processing.
    """
    entry = {
        "original_path": str(original_path),
        "doc_hash": doc_hash,
        "snippet_parts": [str(p) for p in snippet_parts],
        "images": [str(p) for p in images],
        "warnings": warnings or [],
    }
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
