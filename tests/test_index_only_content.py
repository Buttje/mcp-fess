"""Tests for index-only content retrieval from Fess."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from mcp_fess.config import ServerConfig
from mcp_fess.fess_client import FessClient, truncate_text_utf8_safe
from mcp_fess.server import FessServer


@pytest.fixture
def fess_client():
    """Create a test Fess client instance."""
    return FessClient("http://localhost:8080", timeout_ms=30000)


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


# Tests for get_extracted_text_by_doc_id method


@pytest.mark.asyncio
async def test_get_extracted_text_content_field(fess_client):
    """Test that content field is preferred when available."""
    doc_id = "test_doc_1"
    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "content": "This is the content field",
                "body": "This is the body field",
                "digest": "This is the digest field",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id)
        assert text == "This is the content field"
        # Verify search was called correctly
        fess_client.search.assert_called_once_with(
            query=f"doc_id:{doc_id}", label_filter=None, num=1, start=0
        )


@pytest.mark.asyncio
async def test_get_extracted_text_body_field_fallback(fess_client):
    """Test that body field is used when content is missing."""
    doc_id = "test_doc_2"
    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "body": "This is the body field",
                "digest": "This is the digest field",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id)
        assert text == "This is the body field"


@pytest.mark.asyncio
async def test_get_extracted_text_digest_field_fallback(fess_client):
    """Test that digest field is used when content and body are missing."""
    doc_id = "test_doc_3"
    mock_search_result = {"data": [{"doc_id": doc_id, "digest": "This is the digest field"}]}

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id)
        assert text == "This is the digest field"


@pytest.mark.asyncio
async def test_get_extracted_text_empty_content_falls_back_to_body(fess_client):
    """Test that empty content field falls back to body."""
    doc_id = "test_doc_4"
    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "content": "",  # Empty string
                "body": "This is the body field",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id)
        assert text == "This is the body field"


@pytest.mark.asyncio
async def test_get_extracted_text_whitespace_only_falls_back(fess_client):
    """Test that whitespace-only content falls back to next field."""
    doc_id = "test_doc_5"
    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "content": "   \n\t  ",  # Whitespace only
                "body": "This is the body field",
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id)
        # After strip(), empty string should fall back to body
        assert text == "This is the body field"


@pytest.mark.asyncio
async def test_get_extracted_text_handles_list_content(fess_client):
    """Test that list content fields are properly normalized."""
    doc_id = "test_doc_6"
    mock_search_result = {
        "data": [{"doc_id": doc_id, "content": ["First paragraph", "Second paragraph"]}]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id)
        assert text == "First paragraph\n\nSecond paragraph"


@pytest.mark.asyncio
async def test_get_extracted_text_document_not_found(fess_client):
    """Test error when document is not found."""
    doc_id = "nonexistent"
    mock_search_result = {"data": []}

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(ValueError, match="Document not found for doc_id=nonexistent"):
            await fess_client.get_extracted_text_by_doc_id(doc_id)


@pytest.mark.asyncio
async def test_get_extracted_text_no_text_available(fess_client):
    """Test error when document has no extractable text."""
    doc_id = "test_doc_7"
    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "title": "Test Document",
                # No content, body, or digest fields
            }
        ]
    }

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(
            ValueError,
            match="No extracted text available in Fess index for doc_id=test_doc_7.*"
            "Ensure Fess is configured to store extracted content",
        ):
            await fess_client.get_extracted_text_by_doc_id(doc_id)


@pytest.mark.asyncio
async def test_get_extracted_text_with_label_filter(fess_client):
    """Test that label filter is properly applied."""
    doc_id = "test_doc_8"
    label_filter = "hr"
    mock_search_result = {"data": [{"doc_id": doc_id, "content": "HR document content"}]}

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        text = await fess_client.get_extracted_text_by_doc_id(doc_id, label_filter=label_filter)
        assert text == "HR document content"
        # Verify label_filter was passed to search
        fess_client.search.assert_called_once_with(
            query=f"doc_id:{doc_id}", label_filter=label_filter, num=1, start=0
        )


# Tests for UTF-8 safe truncation


def test_truncate_text_utf8_safe_no_truncation():
    """Test truncation when text is within limit."""
    text = "Short text"
    result, was_truncated = truncate_text_utf8_safe(text, 100)
    assert result == text
    assert was_truncated is False


def test_truncate_text_utf8_safe_ascii():
    """Test truncation of ASCII text."""
    text = "A" * 200
    result, was_truncated = truncate_text_utf8_safe(text, 100)
    assert len(result.encode("utf-8")) <= 100
    assert was_truncated is True
    assert len(result) == 100  # ASCII: 1 byte per char


def test_truncate_text_utf8_safe_multibyte():
    """Test truncation doesn't split multibyte UTF-8 sequences."""
    # Use Japanese characters (3 bytes each in UTF-8)
    text = "あ" * 50  # 50 characters = 150 bytes
    result, was_truncated = truncate_text_utf8_safe(text, 100)
    
    # Should not raise UnicodeDecodeError
    assert isinstance(result, str)
    assert was_truncated is True
    
    # Result should be valid UTF-8 and not exceed limit
    encoded = result.encode("utf-8")
    assert len(encoded) <= 100
    
    # Should contain complete characters only (33 chars = 99 bytes)
    assert len(result) == 33


def test_truncate_text_utf8_safe_emoji():
    """Test truncation with emoji (4-byte UTF-8 sequences)."""
    # Emoji are typically 4 bytes in UTF-8
    text = "😀" * 30  # 30 emoji = 120 bytes
    result, was_truncated = truncate_text_utf8_safe(text, 50)
    
    assert isinstance(result, str)
    assert was_truncated is True
    
    # Result should be valid UTF-8 and not exceed limit
    encoded = result.encode("utf-8")
    assert len(encoded) <= 50
    
    # Should contain complete emoji only (12 emoji = 48 bytes)
    assert len(result) == 12


def test_truncate_text_utf8_safe_empty_string():
    """Test truncation of empty string."""
    text = ""
    result, was_truncated = truncate_text_utf8_safe(text, 100)
    assert result == ""
    assert was_truncated is False


def test_truncate_text_utf8_safe_mixed_content():
    """Test truncation with mixed ASCII and multibyte characters."""
    text = "Hello 世界 " * 20  # Mixed English and Chinese
    result, was_truncated = truncate_text_utf8_safe(text, 100)
    
    assert isinstance(result, str)
    encoded = result.encode("utf-8")
    assert len(encoded) <= 100


# Tests for fetch_document_content (now index-only)


@pytest.mark.asyncio
async def test_fetch_document_content_requires_doc_id(fess_client):
    """Test that fetch_document_content now requires doc_id."""
    from mcp_fess.config import ContentFetchConfig

    config = ContentFetchConfig(enabled=True)
    
    with pytest.raises(ValueError, match="Document ID is required for content retrieval"):
        await fess_client.fetch_document_content("http://example.com/doc.html", config)


@pytest.mark.asyncio
async def test_fetch_document_content_index_only(fess_client):
    """Test that fetch_document_content uses index-only retrieval."""
    from mcp_fess.config import ContentFetchConfig

    doc_id = "test_doc_9"
    url = "http://example.com/doc.html"
    config = ContentFetchConfig(enabled=True)
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": "Indexed content"}]}

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        content, content_hash = await fess_client.fetch_document_content(url, config, doc_id=doc_id)
        
        assert content == "Indexed content"
        assert len(content_hash) == 64  # SHA256 hex digest length


@pytest.mark.asyncio
async def test_fetch_document_content_file_url_index_only(fess_client):
    """Test that file:// URLs are also handled via index."""
    from mcp_fess.config import ContentFetchConfig

    doc_id = "test_doc_10"
    url = "file:///path/to/doc.txt"
    config = ContentFetchConfig(enabled=True)
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": "File content from index"}]}

    with patch.object(
        fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        content, content_hash = await fess_client.fetch_document_content(url, config, doc_id=doc_id)
        
        assert content == "File content from index"
        # Verify no HTTP client was created (no actual file access)


# Tests for server handlers


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_index_only(fess_server):
    """Test that fetch_content_chunk uses index-only retrieval."""
    doc_id = "test_doc_11"
    content = "A" * 200  # 200 characters
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 100}
        )
        result = json.loads(result_json)
        
        assert result["content"] == "A" * 100
        assert result["hasMore"] is True
        assert result["totalLength"] == 200
        
        # Verify search was called (not fetch_document_content with URL)
        fess_server.fess_client.search.assert_called()


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_enforces_max_chunk_bytes(fess_server):
    """Test that fetch_content_chunk enforces maxChunkBytes limit on length."""
    doc_id = "test_doc_12"
    content = "A" * 500
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        # Request more than maxChunkBytes (100)
        result_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 200}
        )
        result = json.loads(result_json)
        
        # Should be capped at maxChunkBytes (100)
        assert len(result["content"]) == 100


@pytest.mark.asyncio
async def test_handle_fetch_content_by_id_index_only(fess_server):
    """Test that fetch_content_by_id uses index-only retrieval."""
    doc_id = "test_doc_13"
    content = "Full document content"
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
        result = json.loads(result_json)
        
        assert result["content"] == content
        assert result["truncated"] is False
        
        # Verify search was called
        fess_server.fess_client.search.assert_called()


@pytest.mark.asyncio
async def test_handle_fetch_content_by_id_utf8_safe_truncation(fess_server):
    """Test that fetch_content_by_id uses UTF-8 safe truncation."""
    doc_id = "test_doc_14"
    # Use multibyte characters
    content = "あ" * 50  # 50 characters = 150 bytes
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
        result = json.loads(result_json)
        
        # Should be truncated at 100 bytes (UTF-8 safe)
        assert result["truncated"] is True
        assert len(result["content"].encode("utf-8")) <= 100
        assert "fetch_content_chunk" in result["message"]


@pytest.mark.asyncio
async def test_resource_read_doc_content_index_only(fess_server):
    """Test that the content resource uses index-only retrieval."""
    doc_id = "test_doc_15"
    content = "Document content from index"
    
    mock_search_result = {"data": [{"doc_id": doc_id, "content": content}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        # Access the resource handler directly
        # Note: We can't easily test the decorator, but we can verify the underlying logic
        text = await fess_server.fess_client.get_extracted_text_by_doc_id(doc_id, None)
        
        assert text == content


@pytest.mark.asyncio
async def test_no_http_get_to_document_urls(fess_server):
    """Test that no HTTP GET is made to document URLs."""
    doc_id = "test_doc_16"
    content = "Content from Fess index only"
    
    # Mock document with http:// URL
    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "url": "http://example.com/document.html",  # This URL should NOT be fetched
                "content": content,
            }
        ]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        # Mock httpx to track if any requests are made
        with patch("httpx.AsyncClient") as mock_client_class:
            result_json = await fess_server._handle_fetch_content_chunk(
                {"docId": doc_id, "offset": 0, "length": 100}
            )
            result = json.loads(result_json)
            
            assert result["content"] == content
            # Verify no HTTP client was instantiated (no URL fetch)
            mock_client_class.assert_not_called()


@pytest.mark.asyncio
async def test_consistent_behavior_across_url_schemes(fess_server):
    """Test that content retrieval is consistent regardless of URL scheme."""
    content = "Same content for all schemes"
    
    # Test with different URL schemes
    test_cases = [
        ("file:///path/to/doc.txt", "file_doc"),
        ("http://example.com/doc.html", "http_doc"),
        ("https://secure.example.com/doc.pdf", "https_doc"),
    ]
    
    for url, doc_id in test_cases:
        mock_search_result = {
            "data": [{"doc_id": doc_id, "url": url, "content": content}]
        }
        
        with patch.object(
            fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
        ):
            result_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
            result = json.loads(result_json)
            
            # All should return the same content from index
            assert result["content"] == content
            assert result["truncated"] is False
