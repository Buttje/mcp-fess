"""Tests for file:// URL handling in Fess client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
async def test_fetch_document_content_by_id_success(fess_client):
    """Test fetching document content by ID via Fess API."""
    # Mock the search method to return document metadata
    mock_search_result = {
        "data": [
            {
                "doc_id": "test_doc_123",
                "content": "This is the full content of the document from Fess API.",
                "title": "Test Document",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        content, content_hash = await fess_client.fetch_document_content_by_id("test_doc_123")

        assert content == "This is the full content of the document from Fess API."
        assert len(content_hash) == 64  # SHA256 hash


@pytest.mark.asyncio
async def test_fetch_document_content_by_id_with_body_field(fess_client):
    """Test fetching document content by ID using 'body' field fallback."""
    # Mock the search method - content field is empty, but body field has data
    mock_search_result = {
        "data": [
            {
                "doc_id": "test_doc_123",
                "content": "",
                "body": "Content from body field.",
                "title": "Test Document",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        content, content_hash = await fess_client.fetch_document_content_by_id("test_doc_123")

        assert content == "Content from body field."
        assert len(content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_document_content_by_id_with_digest_field(fess_client):
    """Test fetching document content by ID using 'digest' field as last resort."""
    # Mock the search method - only digest field has data
    mock_search_result = {
        "data": [
            {
                "doc_id": "test_doc_123",
                "content": "",
                "body": "",
                "digest": "Content from digest field.",
                "title": "Test Document",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        content, content_hash = await fess_client.fetch_document_content_by_id("test_doc_123")

        assert content == "Content from digest field."


@pytest.mark.asyncio
async def test_fetch_document_content_by_id_not_found(fess_client):
    """Test fetching document content when document doesn't exist."""
    # Mock the search method to return empty results
    mock_search_result = {"data": []}

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(ValueError, match="Document not found in Fess"):
            await fess_client.fetch_document_content_by_id("nonexistent_doc")


@pytest.mark.asyncio
async def test_fetch_document_content_by_id_no_content(fess_client):
    """Test fetching document when it has no retrievable content."""
    # Mock the search method - document exists but has no content fields
    mock_search_result = {
        "data": [
            {
                "doc_id": "test_doc_123",
                "title": "Test Document",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(ValueError, match="has no retrievable content"):
            await fess_client.fetch_document_content_by_id("test_doc_123")


@pytest.mark.asyncio
async def test_fetch_document_content_file_url_with_doc_id(fess_client, content_fetch_config):
    """Test fetching content from file:// URL with document ID fallback."""
    file_url = "file:///home/user/documents/test.txt"
    doc_id = "test_doc_123"

    # Mock the fetch_document_content_by_id method
    mock_content = "Content fetched via Fess API for file:// URL"
    mock_hash = "abc123"

    with patch.object(
        fess_client,
        "fetch_document_content_by_id",
        new=AsyncMock(return_value=(mock_content, mock_hash)),
    ):
        content, content_hash = await fess_client.fetch_document_content(
            file_url, content_fetch_config, doc_id=doc_id
        )

        assert content == mock_content
        assert content_hash == mock_hash


@pytest.mark.asyncio
async def test_fetch_document_content_file_url_without_doc_id(
    fess_client, content_fetch_config
):
    """Test that file:// URL without doc_id raises helpful error."""
    file_url = "file:///home/user/documents/test.txt"

    with pytest.raises(ValueError, match="Cannot fetch file:// URL without document ID"):
        await fess_client.fetch_document_content(file_url, content_fetch_config)


@pytest.mark.asyncio
async def test_fetch_document_content_file_url_api_failure(
    fess_client, content_fetch_config
):
    """Test error handling when Fess API fails for file:// URL."""
    file_url = "file:///home/user/documents/test.txt"
    doc_id = "test_doc_123"

    # Mock the fetch_document_content_by_id to raise an error
    with patch.object(
        fess_client,
        "fetch_document_content_by_id",
        new=AsyncMock(side_effect=Exception("Fess API error")),
    ):
        with pytest.raises(ValueError, match="Unable to fetch content for file:// URL"):
            await fess_client.fetch_document_content(
                file_url, content_fetch_config, doc_id=doc_id
            )


@pytest.mark.asyncio
async def test_fetch_document_content_improved_error_for_invalid_scheme(
    fess_client, content_fetch_config
):
    """Test that invalid scheme error message is improved."""
    with pytest.raises(ValueError, match="Scheme 'ftp' is not allowed.*Allowed schemes"):
        await fess_client.fetch_document_content(
            "ftp://example.com/file.txt", content_fetch_config
        )


@pytest.mark.asyncio
async def test_fetch_document_content_http_still_works(fess_client, content_fetch_config):
    """Test that regular HTTP URL fetching still works normally."""
    http_url = "http://example.com/document.html"
    html_content = b"<html><body>Test content</body></html>"

    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/html"}
    mock_response.content = html_content
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        content, content_hash = await fess_client.fetch_document_content(
            http_url, content_fetch_config
        )

        assert "Test content" in content
        assert len(content_hash) == 64
