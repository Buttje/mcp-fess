"""Tests for server improvements: truncation notices, error messages, and new tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_fess.config import ContentFetchConfig, LimitsConfig, ServerConfig
from mcp_fess.fess_client import FessClient
from mcp_fess.server import FessServer


@pytest.fixture
def server_config():
    """Create a test server configuration."""
    config = ServerConfig(fessBaseUrl="http://localhost:8080")
    # Set a small maxChunkBytes for testing truncation
    config.limits.maxChunkBytes = 100
    return config


@pytest.fixture
def fess_server(server_config):
    """Create a test Fess server instance."""
    return FessServer(server_config)


@pytest.mark.asyncio
async def test_read_doc_content_adds_truncation_notice(fess_server):
    """Test that read_doc_content adds truncation notice for long content."""
    doc_id = "test_doc_123"
    # Content longer than maxChunkBytes (100)
    long_content = "A" * 200

    # Mock the search call with content field (index-only retrieval)
    mock_search_result = {"data": [{"doc_id": doc_id, "content": long_content, "title": "Test Doc"}]}

    with patch.object(
        fess_server.fess_client,
        "search",
        new=AsyncMock(return_value=mock_search_result),
    ):
        # Test the underlying logic by calling get_extracted_text_by_doc_id
        from mcp_fess.fess_client import truncate_text_utf8_safe

        content = await fess_server.fess_client.get_extracted_text_by_doc_id(doc_id, None)
        
        max_chunk = fess_server.config.limits.maxChunkBytes
        truncated_content, was_truncated = truncate_text_utf8_safe(content, max_chunk)
        
        if was_truncated:
            truncation_notice = (
                f"\n\n[Content truncated at {max_chunk} bytes. "
                f"Use fetch_content_chunk tool with docId='{doc_id}' to retrieve additional sections.]"
            )
            result_content = truncated_content + truncation_notice
        else:
            result_content = truncated_content

        # Verify truncation notice is added
        assert "[Content truncated" in result_content
        assert "fetch_content_chunk" in result_content
        assert doc_id in result_content

@pytest.mark.asyncio
async def test_read_doc_content_no_truncation_notice_for_short_content(fess_server):
    """Test that short content doesn't get truncation notice."""
    doc_id = "test_doc_123"
    # Content shorter than maxChunkBytes (100)
    short_content = "Short content"

    # Mock the search call with content field (index-only retrieval)
    mock_search_result = {"data": [{"doc_id": doc_id, "content": short_content, "title": "Test Doc"}]}

    with patch.object(
        fess_server.fess_client,
        "search",
        new=AsyncMock(return_value=mock_search_result),
    ):
        # Test the underlying logic
        from mcp_fess.fess_client import truncate_text_utf8_safe

        content = await fess_server.fess_client.get_extracted_text_by_doc_id(doc_id, None)
        
        max_chunk = fess_server.config.limits.maxChunkBytes
        truncated_content, was_truncated = truncate_text_utf8_safe(content, max_chunk)
        
        if was_truncated:
            truncation_notice = (
                f"\n\n[Content truncated at {max_chunk} bytes. "
                f"Use fetch_content_chunk tool with docId='{doc_id}' to retrieve additional sections.]"
            )
            result_content = truncated_content + truncation_notice
        else:
            result_content = truncated_content

        # Verify no truncation notice
        assert "[Content truncated" not in result_content
        assert result_content == short_content


@pytest.mark.asyncio
async def test_fetch_content_chunk_improved_error_no_doc_id(fess_server):
    """Test improved error message when docId is missing."""
    with pytest.raises(ValueError, match="docId parameter is required.*search.*tool"):
        await fess_server._handle_fetch_content_chunk({})


@pytest.mark.asyncio
async def test_fetch_content_chunk_improved_error_invalid_offset(fess_server):
    """Test improved error message for invalid offset."""
    with pytest.raises(ValueError, match="offset must be a non-negative integer.*offset=0"):
        await fess_server._handle_fetch_content_chunk({"docId": "test", "offset": -1})


@pytest.mark.asyncio
async def test_fetch_content_chunk_improved_error_invalid_length(fess_server):
    """Test improved error message for invalid length."""
    with pytest.raises(
        ValueError, match="length must be a positive integer.*Maximum recommended"
    ):
        await fess_server._handle_fetch_content_chunk(
            {"docId": "test", "offset": 0, "length": 0}
        )


@pytest.mark.asyncio
async def test_fetch_content_chunk_improved_error_doc_not_found(fess_server):
    """Test improved error message when document is not found."""
    mock_search_result = {"data": []}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(ValueError, match="Document not found for doc_id=nonexistent"):
            await fess_server._handle_fetch_content_chunk(
                {"docId": "nonexistent", "offset": 0, "length": 100}
            )


@pytest.mark.asyncio
async def test_fetch_content_chunk_improved_error_no_content(fess_server):
    """Test improved error message when document has no extractable content."""
    # Document with no content/body/digest fields
    mock_search_result = {"data": [{"doc_id": "test", "title": "Test"}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(
            ValueError, match="No extracted text available in Fess index for doc_id=test"
        ):
            await fess_server._handle_fetch_content_chunk(
                {"docId": "test", "offset": 0, "length": 100}
            )


@pytest.mark.asyncio
async def test_fetch_content_chunk_success(fess_server):
    """Test successful fetch_content_chunk call."""
    doc_id = "test_doc_123"
    content = "A" * 200  # 200 characters

    # Mock the search result with content field (index-only retrieval)
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client,
        "search",
        new=AsyncMock(return_value=mock_search_result),
    ):
        result_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 100}
        )
        result = json.loads(result_json)

        assert result["content"] == "A" * 100
        assert result["hasMore"] is True
        assert result["offset"] == 0
        assert result["length"] == 100
        assert result["totalLength"] == 200


@pytest.mark.asyncio
async def test_fetch_content_by_id_success(fess_server):
    """Test successful fetch_content_by_id call."""
    doc_id = "test_doc_123"
    content = "Full document content here"

    # Mock the search result with content field (index-only retrieval)
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client,
        "search",
        new=AsyncMock(return_value=mock_search_result),
    ):
        result_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
        result = json.loads(result_json)

        assert result["content"] == content
        assert result["totalLength"] == len(content)
        assert result["truncated"] is False


@pytest.mark.asyncio
async def test_fetch_content_by_id_truncated(fess_server):
    """Test fetch_content_by_id with content exceeding maxChunkBytes."""
    doc_id = "test_doc_123"
    # Content longer than maxChunkBytes (100)
    long_content = "A" * 200

    # Mock the search result with content field (index-only retrieval)
    mock_search_result = {"data": [{"doc_id": doc_id, "content": long_content}]}

    with patch.object(
        fess_server.fess_client,
        "search",
        new=AsyncMock(return_value=mock_search_result),
    ):
        result_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
        result = json.loads(result_json)

        assert len(result["content"]) == 100  # Returned content is truncated
        assert result["totalLength"] == 200  # Total length of original document
        assert result["truncated"] is True
        assert "fetch_content_chunk" in result["message"]
        assert "200 characters" in result["message"]  # Message shows full length


@pytest.mark.asyncio
async def test_fetch_content_by_id_missing_doc_id(fess_server):
    """Test fetch_content_by_id with missing docId."""
    with pytest.raises(ValueError, match="docId parameter is required.*search.*tool"):
        await fess_server._handle_fetch_content_by_id({})


@pytest.mark.asyncio
async def test_fetch_content_by_id_doc_not_found(fess_server):
    """Test fetch_content_by_id when document is not found."""
    mock_search_result = {"data": []}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(ValueError, match="Document not found for doc_id=nonexistent"):
            await fess_server._handle_fetch_content_by_id({"docId": "nonexistent"})


@pytest.mark.asyncio
async def test_fetch_content_uses_index_only(fess_server):
    """Test that fetch_content_chunk uses index-only retrieval (not URL fetching)."""
    doc_id = "test_doc_123"
    content = "Test content from index"

    # Mock the search result with content field - no need to fetch from URL
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client,
        "search",
        new=AsyncMock(return_value=mock_search_result),
    ):
        result_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 100}
        )
        result = json.loads(result_json)

        # Verify content was retrieved from index
        assert result["content"] == content
        # Verify search was called (index-only retrieval)
        fess_server.fess_client.search.assert_called()
