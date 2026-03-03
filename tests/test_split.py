"""Tests for md_writer split functionality (strict < 10 MiB per part)."""

from pathlib import Path

from mcp_fess.snippet_engine.md_writer import MAX_BYTES, write_snippets


def test_single_file_small(tmp_path: Path) -> None:
    original = Path("/fake/doc.txt")
    page_lines = [(1, f"line {i}") for i in range(10)]
    parts = write_snippets(original, page_lines, tmp_path, "abc123")
    assert len(parts) == 1
    assert parts[0].exists()
    assert parts[0].stat().st_size < MAX_BYTES


def test_header_present_in_all_parts(tmp_path: Path) -> None:
    original = Path("/fake/doc.txt")
    # Create enough lines to force splitting at 1024 max_bytes
    max_bytes = 1024
    page_lines = [(1, "A" * 100) for _ in range(20)]
    parts = write_snippets(original, page_lines, tmp_path, "abc123", max_bytes=max_bytes)
    for part in parts:
        content = part.read_text(encoding="utf-8")
        assert str(original) in content
        assert "{p<number>:= Page number; l<number>:= Line number}" in content


def test_all_parts_under_max_bytes(tmp_path: Path) -> None:
    original = Path("/fake/bigdoc.txt")
    max_bytes = 2048
    # Lines large enough to force multiple parts
    page_lines = [(1, "B" * 200) for _ in range(20)]
    parts = write_snippets(original, page_lines, tmp_path, "xyz789", max_bytes=max_bytes)
    assert len(parts) > 1
    for part in parts:
        assert part.stat().st_size < max_bytes


def test_continuous_line_numbers(tmp_path: Path) -> None:
    """Line numbers must be continuous across parts."""
    original = Path("/fake/doc.txt")
    max_bytes = 512
    n_lines = 30
    page_lines = [(1, f"line content {i}") for i in range(n_lines)]
    parts = write_snippets(original, page_lines, tmp_path, "lnum01", max_bytes=max_bytes)
    assert len(parts) > 1

    all_line_nums: list[int] = []
    for part in parts:
        content = part.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("p") and " l" in line and ": " in line:
                # Format: p{page} l{line}: {text}
                try:
                    lpart = line.split(" l")[1].split(":")[0]
                    all_line_nums.append(int(lpart))
                except (IndexError, ValueError):
                    pass

    # Should be continuous from 1 to n_lines
    assert all_line_nums == list(range(1, n_lines + 1))


def test_empty_document(tmp_path: Path) -> None:
    original = Path("/fake/empty.txt")
    parts = write_snippets(original, [], tmp_path, "empty1")
    assert len(parts) == 1
    content = parts[0].read_text(encoding="utf-8")
    assert str(original) in content


def test_part_naming(tmp_path: Path) -> None:
    original = Path("/fake/myfile.txt")
    max_bytes = 200
    page_lines = [(1, "X" * 50) for _ in range(10)]
    parts = write_snippets(original, page_lines, tmp_path, "hash01", max_bytes=max_bytes)
    for i, part in enumerate(parts, start=1):
        assert f"part{i:04d}" in part.name
        assert "hash01" in part.name
