"""Tests for ODT text and image extraction."""

from pathlib import Path
from unittest.mock import patch

import pytest


def _make_tiny_png() -> bytes:
    """Create a minimal valid 1x1 pixel PNG image."""
    import struct
    import zlib

    def mk_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + chunk_type + data
        return c + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)

    ihdr = mk_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = mk_chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    iend = mk_chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def _create_odt(tmp_path: Path, paragraphs: list[str], add_image: bool = False) -> Path:
    """Create a minimal ODT file with the given paragraphs."""
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    doc = OpenDocumentText()
    for text in paragraphs:
        doc.text.addElement(P(text=text))
    if add_image:
        doc.addPictureFromString(_make_tiny_png(), "image/png")
    odt_path = tmp_path / "test.odt"
    doc.save(str(odt_path))
    return odt_path


# ---------------------------------------------------------------------------
# extract_odt - text extraction
# ---------------------------------------------------------------------------


def test_extract_odt_returns_text_lines(tmp_path: Path) -> None:
    odt_path = _create_odt(tmp_path, ["Hello ODT world", "Second paragraph"])
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.odt_extract import extract_odt

    lines, images = extract_odt(odt_path, images_root, "abc123")

    texts = [t for _, t in lines]
    assert "Hello ODT world" in texts
    assert "Second paragraph" in texts
    assert images == []


def test_extract_odt_all_lines_on_page_1(tmp_path: Path) -> None:
    odt_path = _create_odt(tmp_path, ["Line A", "Line B", "Line C"])
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.odt_extract import extract_odt

    lines, _ = extract_odt(odt_path, images_root, "abc123")

    assert all(page == 1 for page, _ in lines)


def test_extract_odt_empty_document(tmp_path: Path) -> None:
    odt_path = _create_odt(tmp_path, [])
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.odt_extract import extract_odt

    lines, images = extract_odt(odt_path, images_root, "abc123")

    assert lines == []
    assert images == []


def test_extract_odt_with_image(tmp_path: Path) -> None:
    odt_path = _create_odt(tmp_path, ["Para with image"], add_image=True)
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.odt_extract import extract_odt

    lines, images = extract_odt(odt_path, images_root, "abc123")

    assert len(images) == 1
    assert images[0].exists()
    image_lines = [t for _, t in lines if t.startswith("<IMAGE:")]
    assert len(image_lines) == 1


def test_extract_odt_missing_odfpy(tmp_path: Path) -> None:
    """When odfpy is not installed, extraction should return empty results."""
    odt_path = tmp_path / "test.odt"
    odt_path.write_bytes(b"fake content")
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.odt_extract import extract_odt

    with patch.dict("sys.modules", {"odf": None, "odf.opendocument": None, "odf.text": None}):
        lines, images = extract_odt(odt_path, images_root, "abc123")

    assert lines == []
    assert images == []


def test_extract_odt_invalid_file(tmp_path: Path) -> None:
    """A corrupt/non-ODT file should return empty results without raising."""
    bad_path = tmp_path / "bad.odt"
    bad_path.write_bytes(b"not a valid odt file")
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.odt_extract import extract_odt

    lines, images = extract_odt(bad_path, images_root, "abc123")

    assert lines == []
    assert images == []


# ---------------------------------------------------------------------------
# convert_document dispatcher
# ---------------------------------------------------------------------------


def test_convert_document_dispatches_odt(tmp_path: Path) -> None:
    odt_path = _create_odt(tmp_path, ["Dispatcher test"])
    images_root = tmp_path / "images"
    images_root.mkdir()

    from mcp_fess.snippet_engine.convert import convert_document
    from mcp_fess.snippet_engine.image_store import compute_doc_hash

    doc_hash = compute_doc_hash(odt_path)
    lines, _ = convert_document(odt_path, images_root, doc_hash)

    texts = [t for _, t in lines]
    assert "Dispatcher test" in texts


# ---------------------------------------------------------------------------
# scan_directory includes .odt
# ---------------------------------------------------------------------------


def test_scan_directory_includes_odt(tmp_path: Path) -> None:
    (tmp_path / "doc.odt").write_bytes(b"fake odt")
    (tmp_path / "doc.txt").write_text("plain text", encoding="utf-8")
    (tmp_path / "doc.xyz").write_bytes(b"unknown")

    from mcp_fess.snippet_engine.scan import scan_directory

    found = scan_directory(tmp_path)
    names = {p.name for p in found}
    assert "doc.odt" in names
    assert "doc.txt" in names
    assert "doc.xyz" not in names


def test_odt_in_supported_extensions() -> None:
    from mcp_fess.snippet_engine.scan import SUPPORTED_EXTENSIONS

    assert ".odt" in SUPPORTED_EXTENSIONS


@pytest.mark.parametrize(
    "filename",
    ["report.ODT", "report.Odt"],
)
def test_scan_directory_odt_case_insensitive(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_bytes(b"fake odt")

    from mcp_fess.snippet_engine.scan import scan_directory

    found = scan_directory(tmp_path)
    assert len(found) == 1
