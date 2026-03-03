"""Tests for manifest helpers: load, is_in_manifest, remove_document."""

import json
from pathlib import Path

import pytest

from mcp_fess.snippet_engine.manifest import (
    append_manifest_entry,
    is_document_in_manifest,
    load_manifest_entries,
    remove_document_from_manifest,
)


@pytest.fixture()
def tmp_manifest(tmp_path: Path) -> Path:
    """Return a path to a (not-yet-existing) manifest file inside tmp_path."""
    return tmp_path / "manifest.jsonl"


# ---------------------------------------------------------------------------
# load_manifest_entries
# ---------------------------------------------------------------------------


def test_load_manifest_entries_missing_file(tmp_manifest: Path) -> None:
    assert load_manifest_entries(tmp_manifest) == []


def test_load_manifest_entries_empty_file(tmp_manifest: Path) -> None:
    tmp_manifest.write_text("", encoding="utf-8")
    assert load_manifest_entries(tmp_manifest) == []


def test_load_manifest_entries_single_entry(tmp_path: Path, tmp_manifest: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    append_manifest_entry(tmp_manifest, doc, "abc123", [], [])
    entries = load_manifest_entries(tmp_manifest)
    assert len(entries) == 1
    assert entries[0]["original_path"] == str(doc)


def test_load_manifest_entries_skips_invalid_json(tmp_manifest: Path) -> None:
    tmp_manifest.write_text('{"valid": true}\nnot_json\n', encoding="utf-8")
    entries = load_manifest_entries(tmp_manifest)
    assert len(entries) == 1
    assert entries[0]["valid"] is True


# ---------------------------------------------------------------------------
# is_document_in_manifest
# ---------------------------------------------------------------------------


def test_is_document_in_manifest_false_when_empty(tmp_manifest: Path, tmp_path: Path) -> None:
    doc = tmp_path / "missing.txt"
    assert is_document_in_manifest(tmp_manifest, doc) is False


def test_is_document_in_manifest_true_after_append(tmp_path: Path, tmp_manifest: Path) -> None:
    doc = tmp_path / "report.pdf"
    doc.write_text("content", encoding="utf-8")
    append_manifest_entry(tmp_manifest, doc, "deadbeef", [], [])
    assert is_document_in_manifest(tmp_manifest, doc) is True


def test_is_document_in_manifest_false_for_different_path(
    tmp_path: Path, tmp_manifest: Path
) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("a", encoding="utf-8")
    append_manifest_entry(tmp_manifest, doc_a, "aaaaaa", [], [])
    assert is_document_in_manifest(tmp_manifest, doc_b) is False


# ---------------------------------------------------------------------------
# remove_document_from_manifest
# ---------------------------------------------------------------------------


def test_remove_document_not_found_returns_found_false(
    tmp_path: Path, tmp_manifest: Path
) -> None:
    # Manifest with one entry for doc_a; try to remove doc_b
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("a", encoding="utf-8")
    append_manifest_entry(tmp_manifest, doc_a, "aaaaaa", [], [])

    result = remove_document_from_manifest(tmp_manifest, doc_b)
    assert result["found"] is False
    assert result["removed_parts"] == 0
    assert result["removed_images"] == 0

    # Original entry should still be in manifest
    entries = load_manifest_entries(tmp_manifest)
    assert len(entries) == 1


def test_remove_document_deletes_snippet_files(tmp_path: Path, tmp_manifest: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello world", encoding="utf-8")

    # Create fake snippet parts
    part1 = tmp_path / "doc_abc.part0001.md"
    part2 = tmp_path / "doc_abc.part0002.md"
    part1.write_text("# part1", encoding="utf-8")
    part2.write_text("# part2", encoding="utf-8")

    append_manifest_entry(tmp_manifest, doc, "abc", [part1, part2], [])

    result = remove_document_from_manifest(tmp_manifest, doc)

    assert result["found"] is True
    assert result["removed_parts"] == 2
    assert result["removed_images"] == 0
    assert not part1.exists()
    assert not part2.exists()
    # Manifest should now be empty
    assert load_manifest_entries(tmp_manifest) == []


def test_remove_document_deletes_image_files(tmp_path: Path, tmp_manifest: Path) -> None:
    doc = tmp_path / "doc.pdf"
    doc.write_text("pdf content", encoding="utf-8")

    img1 = tmp_path / "images" / "img1.png"
    img1.parent.mkdir()
    img1.write_bytes(b"\x89PNG")

    append_manifest_entry(tmp_manifest, doc, "xyz", [], [img1])

    result = remove_document_from_manifest(tmp_manifest, doc)

    assert result["found"] is True
    assert result["removed_images"] == 1
    assert not img1.exists()


def test_remove_document_keeps_other_entries(tmp_path: Path, tmp_manifest: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("a", encoding="utf-8")
    doc_b.write_text("b", encoding="utf-8")

    part_a = tmp_path / "a.part0001.md"
    part_a.write_text("# a", encoding="utf-8")

    append_manifest_entry(tmp_manifest, doc_a, "aaa", [part_a], [])
    append_manifest_entry(tmp_manifest, doc_b, "bbb", [], [])

    result = remove_document_from_manifest(tmp_manifest, doc_a)

    assert result["found"] is True
    # doc_b entry must remain
    remaining = load_manifest_entries(tmp_manifest)
    assert len(remaining) == 1
    assert remaining[0]["original_path"] == str(doc_b)


def test_remove_document_handles_missing_snippet_file(tmp_path: Path, tmp_manifest: Path) -> None:
    """Remove should succeed even if a listed snippet file no longer exists."""
    doc = tmp_path / "doc.txt"
    doc.write_text("text", encoding="utf-8")
    ghost = tmp_path / "ghost.part0001.md"
    # ghost file is NOT created on disk

    append_manifest_entry(tmp_manifest, doc, "zzz", [ghost], [])

    result = remove_document_from_manifest(tmp_manifest, doc)
    assert result["found"] is True
    # Count should be 0 because the file didn't exist
    assert result["removed_parts"] == 0


# ---------------------------------------------------------------------------
# Duplicate-skip integration (generate_snippets skips already-processed docs)
# ---------------------------------------------------------------------------


def test_generate_snippets_skips_duplicate(tmp_path: Path) -> None:
    """_handle_generate_snippets must skip a file that is already in manifest."""
    import asyncio
    from unittest.mock import patch

    from mcp_fess.config import ServerConfig
    from mcp_fess.server import FessServer

    config = ServerConfig(fessBaseUrl="http://localhost:8080")
    config.fessComposePath = "/fake/compose.yml"
    server = FessServer(config)

    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    doc = input_dir / "existing.txt"
    doc.write_text("Hello duplicate", encoding="utf-8")

    snippets_root = tmp_path / "snippets"
    images_root = snippets_root / "images"
    snippets_root.mkdir(parents=True)
    images_root.mkdir(parents=True)

    manifest_path = snippets_root / "manifest.jsonl"
    # Pre-populate manifest with this document
    append_manifest_entry(manifest_path, doc, "pre123", [], [])

    with patch(
        "mcp_fess.snippet_engine.compose_parser.find_host_fess_data_dir",
        return_value=tmp_path,
    ):
        result_json = asyncio.get_event_loop().run_until_complete(
            server._handle_generate_snippets(
                {
                    "inputDir": str(input_dir),
                    "outputFolder": "snippets",
                }
            )
        )

    result = json.loads(result_json)
    assert "error" not in result
    assert result["skipped"] == 1
    assert result["processed"] == 0
