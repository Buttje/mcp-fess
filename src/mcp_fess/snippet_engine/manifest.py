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


def load_manifest_entries(manifest_path: Path) -> list[dict]:
    """Load all entries from a manifest.jsonl file.

    Args:
        manifest_path: Path to the manifest.jsonl file.

    Returns:
        List of parsed manifest entry dicts (empty list if file does not exist).
    """
    if not manifest_path.exists():
        return []
    entries: list[dict] = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid JSON line in manifest: %s", line[:80])
    return entries


def is_document_in_manifest(manifest_path: Path, original_path: Path) -> bool:
    """Return True if *original_path* already has an entry in the manifest.

    Args:
        manifest_path: Path to the manifest.jsonl file.
        original_path: Absolute path of the source document to look up.
    """
    original_str = str(original_path)
    for entry in load_manifest_entries(manifest_path):
        if entry.get("original_path") == original_str:
            return True
    return False


def remove_document_from_manifest(manifest_path: Path, original_path: Path) -> dict:
    """Remove a document's manifest entry and delete its generated snippet and image files.

    The original source document is *not* touched.

    Args:
        manifest_path: Path to the manifest.jsonl file.
        original_path: Absolute path of the source document whose artifacts should be removed.

    Returns:
        Dict with keys ``removed_parts``, ``removed_images`` (counts of deleted files) and
        ``found`` (True if a matching manifest entry was found).
        If no matching entry is found all counts are 0 and ``found`` is False.
    """
    entries = load_manifest_entries(manifest_path)
    original_str = str(original_path)

    removed_parts = 0
    removed_images = 0
    found = False
    remaining: list[dict] = []

    for entry in entries:
        if entry.get("original_path") == original_str:
            found = True
            for part_path in entry.get("snippet_parts", []):
                p = Path(part_path)
                if p.exists():
                    p.unlink()
                    removed_parts += 1
                    logger.debug("Deleted snippet part: %s", p)
            for img_path in entry.get("images", []):
                p = Path(img_path)
                if p.exists():
                    p.unlink()
                    removed_images += 1
                    logger.debug("Deleted image: %s", p)
        else:
            remaining.append(entry)

    if found and manifest_path.exists():
        with manifest_path.open("w", encoding="utf-8") as f:
            for entry in remaining:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {"found": found, "removed_parts": removed_parts, "removed_images": removed_images}
