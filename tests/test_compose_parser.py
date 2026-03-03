"""Tests for snippet_engine compose_parser."""

import textwrap
from pathlib import Path

import pytest

from mcp_fess.snippet_engine.compose_parser import find_host_fess_data_dir


@pytest.fixture()
def compose_file(tmp_path: Path) -> Path:
    content = textwrap.dedent("""
        services:
          fess01:
            image: ghcr.io/codelibs/fess:latest
            volumes:
              - F:\\Fess_Docs:/data/fess
          other:
            image: other
            volumes:
              - /some/other:/data/other
    """)
    p = tmp_path / "compose.yaml"
    p.write_text(content)
    return p


def test_auto_detect_service(compose_file: Path) -> None:
    result = find_host_fess_data_dir(compose_file)
    assert str(result) == "F:\\Fess_Docs"


def test_explicit_service(compose_file: Path) -> None:
    result = find_host_fess_data_dir(compose_file, service_name="fess01")
    assert str(result) == "F:\\Fess_Docs"


def test_mode_suffix_rw(tmp_path: Path) -> None:
    content = textwrap.dedent("""
        services:
          svc:
            volumes:
              - /host/data:/data/fess:rw
    """)
    p = tmp_path / "compose.yaml"
    p.write_text(content)
    result = find_host_fess_data_dir(p)
    assert str(result) == "/host/data"


def test_mode_suffix_ro(tmp_path: Path) -> None:
    content = textwrap.dedent("""
        services:
          svc:
            volumes:
              - /host/data:/data/fess:ro
    """)
    p = tmp_path / "compose.yaml"
    p.write_text(content)
    result = find_host_fess_data_dir(p)
    assert str(result) == "/host/data"


def test_missing_compose_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        find_host_fess_data_dir(tmp_path / "nonexistent.yaml")


def test_no_matching_mount_raises(tmp_path: Path) -> None:
    content = textwrap.dedent("""
        services:
          svc:
            volumes:
              - /host/data:/data/other
    """)
    p = tmp_path / "compose.yaml"
    p.write_text(content)
    with pytest.raises(ValueError):
        find_host_fess_data_dir(p)


def test_wrong_service_raises(compose_file: Path) -> None:
    with pytest.raises(ValueError):
        find_host_fess_data_dir(compose_file, service_name="nonexistent")
