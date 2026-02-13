"""Tests for Fess client module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_fess.config import ContentFetchConfig
from mcp_fess.fess_client import FessClient


@pytest.fixture
def fess_client():
    """Create a Fess client for testing."""
    return FessClient("http://localhost:8080", timeout_ms=30000)


@pytest.fixture
def content_fetch_config():
    """Create a content fetch config for testing."""
    return ContentFetchConfig()


@pytest.mark.asyncio
async def test_search(fess_client):
    """Test search functionality."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"title": "Test"}]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        result = await fess_client.search("test query", label_filter="test_label")
        assert "data" in result
        assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_suggest(fess_client):
    """Test suggest functionality."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"suggestions": ["test1", "test2"]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        result = await fess_client.suggest("test", label="test_label")
        assert "suggestions" in result


@pytest.mark.asyncio
async def test_popular_words(fess_client):
    """Test popular words functionality."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"words": ["word1", "word2"]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        result = await fess_client.popular_words(label="test_label")
        assert "words" in result


@pytest.mark.asyncio
async def test_list_labels(fess_client):
    """Test list labels functionality."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"labels": [{"name": "test"}]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        result = await fess_client.list_labels()
        assert "labels" in result


@pytest.mark.asyncio
async def test_health(fess_client):
    """Test health check functionality."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "green", "timed_out": False}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        result = await fess_client.health()
        assert result["status"] == "green"
        assert result["timed_out"] is False


def test_is_private_network(fess_client):
    """Test private network detection."""
    assert fess_client._is_private_network("localhost") is True
    assert fess_client._is_private_network("127.0.0.1") is True
    assert fess_client._is_private_network("::1") is True
    assert fess_client._is_private_network("10.0.0.1") is True
    assert fess_client._is_private_network("172.16.0.1") is True
    assert fess_client._is_private_network("192.168.1.1") is True
    assert fess_client._is_private_network("8.8.8.8") is False
    assert fess_client._is_private_network("example.com") is False


def test_extract_text_from_html(fess_client):
    """Test HTML text extraction."""
    html = b"""
    <html>
        <head><title>Test</title></head>
        <body>
            <script>console.log('test');</script>
            <h1>Heading</h1>
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
        </body>
    </html>
    """
    text = fess_client._extract_text_from_html(html)
    assert "Heading" in text
    assert "Paragraph 1" in text
    assert "Paragraph 2" in text
    assert "console.log" not in text


@pytest.mark.asyncio
async def test_fetch_document_content_disabled(fess_client):
    """Test content fetching when disabled."""
    config = ContentFetchConfig(enabled=False)

    with pytest.raises(ValueError, match="Content fetching is disabled"):
        await fess_client.fetch_document_content("http://example.com", config)


@pytest.mark.asyncio
async def test_fetch_document_content_invalid_scheme(fess_client):
    """Test content fetching with invalid scheme."""
    config = ContentFetchConfig(allowedSchemes=["http", "https"])

    with pytest.raises(ValueError, match="Scheme ftp not allowed"):
        await fess_client.fetch_document_content("ftp://example.com", config)


@pytest.mark.asyncio
async def test_fetch_document_content_private_network(fess_client):
    """Test content fetching with private network target."""
    config = ContentFetchConfig(allowPrivateNetworkTargets=False)

    with pytest.raises(ValueError, match="Access to private network target"):
        await fess_client.fetch_document_content("http://localhost/test", config)


@pytest.mark.asyncio
async def test_close(fess_client):
    """Test client cleanup."""
    with patch.object(fess_client.client, "aclose", new=AsyncMock()):
        await fess_client.close()
        fess_client.client.aclose.assert_called_once()
