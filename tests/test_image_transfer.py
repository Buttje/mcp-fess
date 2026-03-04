"""Tests for image transfer via MCP tool and resource."""

import base64
import json
import unittest.mock as mock

import pytest

from mcp_fess.config import DomainConfig, ServerConfig
from mcp_fess.server import FessServer, _mime_type_for_image
from mcp_fess.snippet_engine import compose_parser


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return ServerConfig(
        fessBaseUrl="http://localhost:8080",
        domain=DomainConfig(
            name="Test Domain",
            description="Test description",
        ),
    )


@pytest.fixture
def fess_server(test_config):
    """Create a FessServer instance for testing."""
    return FessServer(test_config)


# ---------------------------------------------------------------------------
# _mime_type_for_image
# ---------------------------------------------------------------------------


def test_mime_type_for_image_png(tmp_path):
    img = tmp_path / "test_image.png"
    img.write_bytes(b"")
    assert _mime_type_for_image(img) == "image/png"


def test_mime_type_for_image_jpeg(tmp_path):
    img = tmp_path / "test_image.jpg"
    img.write_bytes(b"")
    assert _mime_type_for_image(img) == "image/jpeg"


def test_mime_type_for_image_jpeg_ext(tmp_path):
    img = tmp_path / "test_image.jpeg"
    img.write_bytes(b"")
    assert _mime_type_for_image(img) == "image/jpeg"


def test_mime_type_for_image_unknown_defaults_to_png(tmp_path):
    img = tmp_path / "test_image.bin"
    img.write_bytes(b"")
    # Unknown extension defaults to image/png
    assert _mime_type_for_image(img) == "image/png"


# ---------------------------------------------------------------------------
# _handle_get_image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_get_image_missing_path(fess_server):
    """Missing imagePath returns error JSON."""
    result = await fess_server._handle_get_image({})
    data = json.loads(result)
    assert "error" in data
    assert "imagePath" in data["error"]


@pytest.mark.asyncio
async def test_handle_get_image_relative_path(fess_server):
    """Relative imagePath returns error JSON."""
    result = await fess_server._handle_get_image({"imagePath": "relative/path.png"})
    data = json.loads(result)
    assert "error" in data
    assert "absolute" in data["error"].lower()


@pytest.mark.asyncio
async def test_handle_get_image_nonexistent_file(fess_server, tmp_path):
    """Nonexistent file returns error JSON."""
    missing = tmp_path / "missing.png"
    result = await fess_server._handle_get_image({"imagePath": str(missing)})
    data = json.loads(result)
    assert "error" in data
    assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_handle_get_image_success_png(fess_server, tmp_path):
    """Valid PNG file returns base64 data and correct MIME type."""
    img = tmp_path / "abc123_p1_i0_def456.png"
    raw_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20  # fake PNG header
    img.write_bytes(raw_bytes)

    result = await fess_server._handle_get_image({"imagePath": str(img)})
    data = json.loads(result)

    assert "data" in data
    assert data["mimeType"] == "image/png"
    assert data["path"] == str(img.resolve())
    decoded = base64.standard_b64decode(data["data"])
    assert decoded == raw_bytes


@pytest.mark.asyncio
async def test_handle_get_image_success_jpeg(fess_server, tmp_path):
    """Valid JPEG file returns base64 data and correct MIME type."""
    img = tmp_path / "abc123_p1_i0_def456.jpg"
    raw_bytes = b"\xff\xd8\xff" + b"\x00" * 20  # fake JPEG header
    img.write_bytes(raw_bytes)

    result = await fess_server._handle_get_image({"imagePath": str(img)})
    data = json.loads(result)

    assert data["mimeType"] == "image/jpeg"
    decoded = base64.standard_b64decode(data["data"])
    assert decoded == raw_bytes


# ---------------------------------------------------------------------------
# _resolve_image_path
# ---------------------------------------------------------------------------


def test_resolve_image_path_rejects_path_separators(fess_server):
    """image_id with slash raises ValueError."""
    with pytest.raises(ValueError, match="plain filename"):
        fess_server._resolve_image_path("subdir/image.png")


def test_resolve_image_path_rejects_dotdot(fess_server):
    """image_id starting with dot raises ValueError."""
    with pytest.raises(ValueError, match="plain filename"):
        fess_server._resolve_image_path("../etc/passwd")


def test_resolve_image_path_not_found_no_compose(fess_server):
    """Without fessComposePath configured, raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="not found"):
        fess_server._resolve_image_path("abc123_p1_i0_def456.png")


def test_resolve_image_path_finds_file_under_host_data_dir(tmp_path, test_config):
    """When compose returns a host data dir, finds the image by filename."""
    # Create a fake image in a nested images subdirectory
    images_dir = tmp_path / "MY_DOCS" / "images"
    images_dir.mkdir(parents=True)
    img = images_dir / "abc123_p1_i0_def456.png"
    img.write_bytes(b"\x89PNG")

    # Build a config with fessComposePath set to any existing path
    config = ServerConfig(
        fessBaseUrl="http://localhost:8080",
        fessComposePath=str(tmp_path / "docker-compose.yaml"),
        domain=DomainConfig(name="T"),
    )
    server = FessServer(config)

    # Patch find_host_fess_data_dir to return tmp_path
    with mock.patch.object(
        compose_parser,
        "find_host_fess_data_dir",
        return_value=tmp_path,
    ):
        resolved = server._resolve_image_path("abc123_p1_i0_def456.png")
        assert resolved == img
