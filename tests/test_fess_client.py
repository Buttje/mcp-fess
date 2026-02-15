"""Tests for Fess client module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_fess.config import ContentFetchConfig
from mcp_fess.fess_client import FessClient, LabelCache


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


# Additional error handling tests for search
@pytest.mark.asyncio
async def test_search_http_error(fess_client):
    """Test search with HTTP error."""
    import httpx

    mock_error = httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(),
        response=MagicMock(status_code=404),
    )

    with (
        patch.object(fess_client.client, "get", new=AsyncMock(side_effect=mock_error)),
        pytest.raises(httpx.HTTPError),
    ):
        await fess_client.search("test query")


@pytest.mark.asyncio
async def test_search_with_all_params(fess_client):
    """Test search with all parameters."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        fess_client.client, "get", new=AsyncMock(return_value=mock_response)
    ) as mock_get:
        result = await fess_client.search(
            query="test",
            label_filter="label1",
            start=10,
            num=50,
            sort="score.desc",
            lang="en",
            fields=["title", "content"],
            extra_param="value",
        )
        assert "data" in result
        # Verify params were passed
        call_args = mock_get.call_args
        params = call_args.kwargs["params"]
        assert params["q"] == "test"
        assert params["fields.label"] == "label1"
        assert params["start"] == 10
        assert params["num"] == 50
        assert params["sort"] == "score.desc"
        assert params["lang"] == "en"
        assert params["extra_param"] == "value"


@pytest.mark.asyncio
async def test_search_minimal_params(fess_client):
    """Test search with minimal parameters."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        fess_client.client, "get", new=AsyncMock(return_value=mock_response)
    ) as mock_get:
        await fess_client.search("test")
        call_args = mock_get.call_args
        params = call_args.kwargs["params"]
        assert params["q"] == "test"
        assert params["start"] == 0
        assert params["num"] == 20
        assert "fields.label" not in params


# Additional error handling tests for suggest
@pytest.mark.asyncio
async def test_suggest_http_error(fess_client):
    """Test suggest with HTTP error."""
    import httpx

    mock_error = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )

    with (
        patch.object(fess_client.client, "get", new=AsyncMock(side_effect=mock_error)),
        pytest.raises(httpx.HTTPError),
    ):
        await fess_client.suggest("test")


@pytest.mark.asyncio
async def test_suggest_with_all_params(fess_client):
    """Test suggest with all parameters."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"suggestions": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        fess_client.client, "get", new=AsyncMock(return_value=mock_response)
    ) as mock_get:
        result = await fess_client.suggest(
            prefix="test", label="label1", num=20, fields=["title", "content"], lang="en"
        )
        assert "suggestions" in result
        call_args = mock_get.call_args
        params = call_args.kwargs["params"]
        assert params["q"] == "test"
        assert params["label"] == "label1"
        assert params["num"] == 20
        assert params["fields"] == "title,content"
        assert params["lang"] == "en"


# Additional error handling tests for popular_words
@pytest.mark.asyncio
async def test_popular_words_http_error(fess_client):
    """Test popular words with HTTP error."""
    import httpx

    mock_error = httpx.HTTPStatusError(
        "503 Service Unavailable",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )

    with (
        patch.object(fess_client.client, "get", new=AsyncMock(side_effect=mock_error)),
        pytest.raises(httpx.HTTPError),
    ):
        await fess_client.popular_words()


@pytest.mark.asyncio
async def test_popular_words_with_all_params(fess_client):
    """Test popular words with all parameters."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"words": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        fess_client.client, "get", new=AsyncMock(return_value=mock_response)
    ) as mock_get:
        result = await fess_client.popular_words(label="label1", seed=12345, field="content")
        assert "words" in result
        call_args = mock_get.call_args
        params = call_args.kwargs["params"]
        assert params["label"] == "label1"
        assert params["seed"] == 12345
        assert params["field"] == "content"


@pytest.mark.asyncio
async def test_popular_words_no_params(fess_client):
    """Test popular words with no parameters."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"words": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(
        fess_client.client, "get", new=AsyncMock(return_value=mock_response)
    ) as mock_get:
        await fess_client.popular_words()
        call_args = mock_get.call_args
        params = call_args.kwargs["params"]
        assert params == {}


# Additional error handling tests for list_labels
@pytest.mark.asyncio
async def test_list_labels_http_error(fess_client):
    """Test list labels with HTTP error."""
    import httpx

    mock_error = httpx.HTTPStatusError(
        "401 Unauthorized",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )

    with (
        patch.object(fess_client.client, "get", new=AsyncMock(side_effect=mock_error)),
        pytest.raises(httpx.HTTPError),
    ):
        await fess_client.list_labels()


# Additional error handling tests for health
@pytest.mark.asyncio
async def test_health_http_error(fess_client):
    """Test health check with HTTP error."""
    import httpx

    mock_error = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )

    with (
        patch.object(fess_client.client, "get", new=AsyncMock(side_effect=mock_error)),
        pytest.raises(httpx.HTTPError),
    ):
        await fess_client.health()


# Additional tests for _is_private_network
def test_is_private_network_edge_cases(fess_client):
    """Test private network detection edge cases."""
    # Empty hostname
    assert fess_client._is_private_network("") is False

    # IPv6 loopback
    assert fess_client._is_private_network("::1") is True

    # Private IP ranges - edge cases
    assert fess_client._is_private_network("172.15.0.1") is False  # Just below 172.16
    assert fess_client._is_private_network("172.32.0.1") is False  # Just above 172.31
    assert fess_client._is_private_network("172.20.0.1") is True  # In range

    # Invalid IP format
    assert fess_client._is_private_network("256.256.256.256") is False
    assert fess_client._is_private_network("192.168") is False
    assert fess_client._is_private_network("not.an.ip.address") is False


# Comprehensive fetch_document_content tests
@pytest.mark.asyncio
async def test_fetch_document_content_html(fess_client, content_fetch_config):
    """Test fetching HTML content."""
    html_content = b"""
    <html>
        <head><title>Test</title></head>
        <body><h1>Hello</h1><p>World</p></body>
    </html>
    """

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
            "http://example.com", content_fetch_config
        )

        assert "Hello" in content
        assert "World" in content
        assert len(content_hash) == 64  # SHA256 hash


@pytest.mark.asyncio
async def test_fetch_document_content_pdf(fess_client, content_fetch_config):
    """Test fetching PDF content."""
    # Create a minimal valid PDF
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF"""

    mock_response = MagicMock()
    mock_response.headers = {"content-type": "application/pdf"}
    mock_response.content = pdf_content
    mock_response.raise_for_status = MagicMock()

    config = ContentFetchConfig(enablePdf=True)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        content, content_hash = await fess_client.fetch_document_content(
            "http://example.com/doc.pdf", config
        )

        assert "Hello World" in content
        assert len(content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_document_content_pdf_disabled(fess_client):
    """Test fetching PDF content when PDF conversion is disabled."""
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "application/pdf"}
    mock_response.content = b"PDF content"
    mock_response.raise_for_status = MagicMock()

    config = ContentFetchConfig(enablePdf=False)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with pytest.raises(ValueError, match="PDF conversion is disabled"):
            await fess_client.fetch_document_content("http://example.com/doc.pdf", config)


@pytest.mark.asyncio
async def test_fetch_document_content_plain_text(fess_client, content_fetch_config):
    """Test fetching plain text content."""
    text_content = b"Plain text content here"

    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.content = text_content
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        content, content_hash = await fess_client.fetch_document_content(
            "http://example.com/doc.txt", content_fetch_config
        )

        assert content == "Plain text content here"
        assert len(content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_document_content_max_bytes(fess_client):
    """Test fetching content respects maxBytes limit."""
    large_content = b"x" * 2000

    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.content = large_content
    mock_response.raise_for_status = MagicMock()

    config = ContentFetchConfig(maxBytes=1000)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        content, _ = await fess_client.fetch_document_content("http://example.com", config)

        assert len(content) == 1000


@pytest.mark.asyncio
async def test_fetch_document_content_http_error(fess_client, content_fetch_config):
    """Test fetch document content with HTTP error."""
    import httpx

    mock_error = httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(),
        response=MagicMock(status_code=404),
    )

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=mock_error)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        with pytest.raises(httpx.HTTPError):
            await fess_client.fetch_document_content("http://example.com", content_fetch_config)


@pytest.mark.asyncio
async def test_fetch_document_content_allowlist(fess_client):
    """Test fetching content from allowlisted private network."""
    html_content = b"<html><body>Private content</body></html>"

    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/html"}
    mock_response.content = html_content
    mock_response.raise_for_status = MagicMock()

    config = ContentFetchConfig(
        allowPrivateNetworkTargets=False, allowedHostAllowlist=["localhost"]
    )

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        content, _ = await fess_client.fetch_document_content("http://localhost/doc", config)

        assert "Private content" in content


@pytest.mark.asyncio
async def test_fetch_document_content_user_agent(fess_client, content_fetch_config):
    """Test that custom user agent is used."""
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.content = b"content"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await fess_client.fetch_document_content("http://example.com", content_fetch_config)

        # Verify user agent was passed
        call_args = mock_client.get.call_args
        headers = call_args.kwargs["headers"]
        assert "User-Agent" in headers


# Test HTML extraction edge cases
def test_extract_text_from_html_with_script_style(fess_client):
    """Test HTML extraction removes script and style tags."""
    html = b"""
    <html>
        <head>
            <style>body { color: red; }</style>
            <script>alert('test');</script>
        </head>
        <body>
            <p>Visible content</p>
        </body>
    </html>
    """
    text = fess_client._extract_text_from_html(html)
    assert "Visible content" in text
    assert "color: red" not in text
    assert "alert" not in text


def test_extract_text_from_html_invalid(fess_client):
    """Test HTML extraction with invalid HTML."""
    invalid_html = b"\x80\x81\x82 Invalid bytes"
    text = fess_client._extract_text_from_html(invalid_html)
    # Should fall back to decoding as text
    assert isinstance(text, str)


def test_extract_text_from_html_with_meta_link(fess_client):
    """Test HTML extraction removes meta and link tags."""
    html = b"""
    <html>
        <head>
            <meta charset="utf-8">
            <link rel="stylesheet" href="style.css">
        </head>
        <body>
            <p>Content</p>
        </body>
    </html>
    """
    text = fess_client._extract_text_from_html(html)
    assert "Content" in text
    assert "charset" not in text
    assert "stylesheet" not in text


# Test PDF extraction edge cases
def test_extract_text_from_pdf_invalid(fess_client):
    """Test PDF extraction with invalid PDF."""
    invalid_pdf = b"Not a valid PDF"

    with pytest.raises(ValueError, match="PDF parsing failed"):
        fess_client._extract_text_from_pdf(invalid_pdf)


# Label cache tests
@pytest.mark.asyncio
async def test_label_cache_initialization():
    """Test label cache initialization."""
    cache = LabelCache(ttl_seconds=60)
    assert cache.ttl_seconds == 60
    assert await cache.get() == []
    assert cache.is_expired() is True


@pytest.mark.asyncio
async def test_label_cache_set_and_get():
    """Test setting and getting labels from cache."""
    cache = LabelCache(ttl_seconds=60)
    labels = [{"value": "hr", "name": "HR"}]

    await cache.set(labels)
    cached = await cache.get()

    assert cached == labels
    assert cache.is_expired() is False


@pytest.mark.asyncio
async def test_label_cache_expiration():
    """Test label cache expiration."""
    import time

    cache = LabelCache(ttl_seconds=1)
    labels = [{"value": "hr", "name": "HR"}]

    await cache.set(labels)
    assert cache.is_expired() is False

    # Wait for cache to expire
    time.sleep(1.1)
    assert cache.is_expired() is True


@pytest.mark.asyncio
async def test_get_cached_labels_fresh(fess_client):
    """Test getting fresh cached labels."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"value": "hr", "name": "HR"}]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        labels = await fess_client.get_cached_labels()
        assert len(labels) == 1
        assert labels[0]["value"] == "hr"


@pytest.mark.asyncio
async def test_get_cached_labels_uses_cache(fess_client):
    """Test that cached labels are used when not expired."""
    # Prepopulate cache
    cached_labels = [{"value": "cached", "name": "Cached"}]
    await fess_client.label_cache.set(cached_labels)

    # This should return cached data without calling Fess
    labels = await fess_client.get_cached_labels()
    assert labels == cached_labels


@pytest.mark.asyncio
async def test_get_cached_labels_fess_down(fess_client):
    """Test getting cached labels when Fess is down."""
    # Prepopulate cache with stale data
    stale_labels = [{"value": "stale", "name": "Stale"}]
    await fess_client.label_cache.set(stale_labels)

    # Force cache to expire
    fess_client.label_cache._last_fetch = 0

    # Mock Fess error
    with patch.object(
        fess_client.client, "get", new=AsyncMock(side_effect=Exception("Fess down"))
    ):
        labels = await fess_client.get_cached_labels()
        # Should return stale cache
        assert labels == stale_labels


@pytest.mark.asyncio
async def test_get_cached_labels_force_refresh(fess_client):
    """Test force refresh of cached labels."""
    # Prepopulate cache
    old_labels = [{"value": "old", "name": "Old"}]
    await fess_client.label_cache.set(old_labels)

    # Mock fresh data from Fess
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"value": "new", "name": "New"}]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(fess_client.client, "get", new=AsyncMock(return_value=mock_response)):
        labels = await fess_client.get_cached_labels(force_refresh=True)
        assert len(labels) == 1
        assert labels[0]["value"] == "new"
