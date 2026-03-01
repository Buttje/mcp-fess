"""Tests for the server module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_fess.config import DomainConfig, ServerConfig
from mcp_fess.server import FessServer, main


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return ServerConfig(
        fessBaseUrl="http://localhost:8080",
        domain=DomainConfig(
            id="test_domain",
            name="Test Domain",
            description="Test description",
        ),
    )


@pytest.fixture
def fess_server(test_config):
    """Create a FessServer instance for testing."""
    return FessServer(test_config)


def test_main_exists():
    """Test that the main function exists."""
    assert callable(main)


def test_server_initialization(fess_server, test_config):
    """Test server initialization."""
    assert fess_server.domain_id == "test_domain"
    assert fess_server.protocol_version == "2025-03-26"
    assert fess_server.config == test_config


def test_server_initialization_cody_mode(test_config):
    """Test server initialization in Cody mode."""
    server = FessServer(test_config, protocol_version="2024-11-05")
    assert server.protocol_version == "2024-11-05"


def test_get_domain_block(fess_server):
    """Test domain block generation."""
    domain_block = fess_server._get_domain_block()
    assert "[Knowledge Domain]" in domain_block
    assert "id: test_domain" in domain_block
    assert "name: Test Domain" in domain_block
    assert "description: Test description" in domain_block


@pytest.mark.asyncio
async def test_handle_search_missing_query(fess_server):
    """Test search handler with missing query."""
    with pytest.raises(ValueError, match="query parameter is required"):
        await fess_server._handle_search({})


@pytest.mark.asyncio
async def test_handle_search_invalid_page_size(fess_server):
    """Test search handler with invalid page size."""
    with pytest.raises(ValueError, match="pageSize must be a positive integer"):
        await fess_server._handle_search({"query": "test", "pageSize": -1})


@pytest.mark.asyncio
async def test_handle_search_invalid_start(fess_server):
    """Test search handler with invalid start."""
    with pytest.raises(ValueError, match="start must be a non-negative integer"):
        await fess_server._handle_search({"query": "test", "start": -1})


@pytest.mark.asyncio
async def test_handle_search_success(fess_server):
    """Test successful search."""
    mock_result = {"data": [{"title": "Test"}]}

    with patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_search({"query": "test"})
        assert isinstance(result, str)
        assert "Test" in result


@pytest.mark.asyncio
async def test_handle_search_strips_solr_id(fess_server):
    """Test that _id (Solr internal ID) is removed from search results."""
    mock_result = {
        "data": [
            {"_id": "solr-internal-id", "doc_id": "abc123", "title": "Test Doc"},
            {"_id": "another-solr-id", "doc_id": "def456", "title": "Another Doc"},
        ]
    }

    with patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_search({"query": "test"})
        parsed = json.loads(result)
        for doc in parsed["data"]:
            assert "_id" not in doc
            assert "doc_id" in doc


@pytest.mark.asyncio
async def test_handle_search_with_label(fess_server):
    """Test search with explicit label."""
    mock_result = {"data": [{"title": "Test"}]}
    mock_labels = [{"value": "hr", "name": "HR"}]

    with (
        patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)),
        patch.object(
            fess_server.fess_client, "get_cached_labels", new=AsyncMock(return_value=mock_labels)
        ),
    ):
        # Add hr label to config
        from mcp_fess.config import LabelDescriptor

        fess_server.config.labels["hr"] = LabelDescriptor(
            title="HR", description="HR docs", examples=[]
        )

        result = await fess_server._handle_search({"query": "test", "label": "hr"})
        assert isinstance(result, str)
        assert "Test" in result


@pytest.mark.asyncio
async def test_handle_search_with_label_all(fess_server):
    """Test search with label='all'."""
    mock_result = {"data": [{"title": "Test"}]}

    with patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_search({"query": "test", "label": "all"})
        assert isinstance(result, str)
        assert "Test" in result


@pytest.mark.asyncio
async def test_handle_search_invalid_label_strict(fess_server):
    """Test search with invalid label in strict mode."""
    mock_labels = []

    with patch.object(
        fess_server.fess_client, "get_cached_labels", new=AsyncMock(return_value=mock_labels)
    ):
        fess_server.config.strictLabels = True
        with pytest.raises(ValueError, match="Unknown label"):
            await fess_server._handle_search({"query": "test", "label": "invalid"})


@pytest.mark.asyncio
async def test_handle_suggest_missing_prefix(fess_server):
    """Test suggest handler with missing prefix."""
    with pytest.raises(ValueError, match="prefix parameter is required"):
        await fess_server._handle_suggest({})


@pytest.mark.asyncio
async def test_handle_suggest_invalid_num(fess_server):
    """Test suggest handler with invalid num."""
    with pytest.raises(ValueError, match="num must be a positive integer"):
        await fess_server._handle_suggest({"prefix": "test", "num": -1})


@pytest.mark.asyncio
async def test_handle_suggest_success(fess_server):
    """Test successful suggest."""
    mock_result = {"suggestions": ["test1", "test2"]}

    with patch.object(fess_server.fess_client, "suggest", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_suggest({"prefix": "test"})
        assert isinstance(result, str)
        assert "test1" in result


@pytest.mark.asyncio
async def test_handle_popular_words_success(fess_server):
    """Test successful popular words."""
    mock_result = {"words": ["word1", "word2"]}

    with patch.object(
        fess_server.fess_client, "popular_words", new=AsyncMock(return_value=mock_result)
    ):
        result = await fess_server._handle_popular_words({})
        assert isinstance(result, str)
        assert "word1" in result


@pytest.mark.asyncio
async def test_handle_list_labels_success(fess_server):
    """Test successful list labels."""
    mock_labels = [{"value": "hr", "name": "HR Department"}]

    with patch.object(
        fess_server.fess_client, "get_cached_labels", new=AsyncMock(return_value=mock_labels)
    ):
        result = await fess_server._handle_list_labels()
        assert isinstance(result, str)
        assert "all" in result  # "all" should always be included
        assert "defaultLabel" in result


@pytest.mark.asyncio
async def test_handle_list_labels_with_fess_down(fess_server):
    """Test list labels when Fess is down."""
    with patch.object(
        fess_server.fess_client,
        "get_cached_labels",
        new=AsyncMock(side_effect=Exception("Fess down")),
    ):
        result = await fess_server._handle_list_labels()
        assert isinstance(result, str)
        assert "all" in result  # "all" should still be in config
        assert "fessAvailable" in result


@pytest.mark.asyncio
async def test_handle_health_success(fess_server):
    """Test successful health check."""
    mock_result = {"status": "green", "timed_out": False}

    with patch.object(fess_server.fess_client, "health", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_health()
        assert isinstance(result, str)
        assert "green" in result


@pytest.mark.asyncio
async def test_handle_job_get_missing_job_id(fess_server):
    """Test job get handler with missing job ID."""
    with pytest.raises(ValueError, match="jobId parameter is required"):
        await fess_server._handle_job_get({})


@pytest.mark.asyncio
async def test_handle_job_get_not_found(fess_server):
    """Test job get handler with non-existent job."""
    result = await fess_server._handle_job_get({"jobId": "nonexistent"})
    assert isinstance(result, str)
    assert "Job not found" in result


@pytest.mark.asyncio
async def test_handle_job_get_success(fess_server):
    """Test successful job get."""
    fess_server.jobs["test_job"] = {
        "state": "done",
        "progress": 100,
        "message": "Complete",
    }

    result = await fess_server._handle_job_get({"jobId": "test_job"})
    assert isinstance(result, str)
    assert "done" in result
    assert "100" in result


@pytest.mark.asyncio
async def test_cleanup(fess_server):
    """Test server cleanup."""
    with patch.object(fess_server.fess_client, "close", new=AsyncMock()):
        await fess_server.cleanup()
        fess_server.fess_client.close.assert_called_once()


# Test MCP handler integration - These are tested through acceptance tests
# The handlers are internal to the MCP Server framework and not directly testable
# through unit tests. The acceptance tests cover these scenarios.


# Test run_stdio - skip due to complexity of mocking stdio transport
# This is tested in acceptance tests


# Note: run_http tests are skipped because sse_server import doesn't exist in current MCP version
# The code imports from mcp.server.sse import sse_server, but this doesn't exist in mcp 1.26.0


# Test main function scenarios
def test_main_with_stdio():
    """Test main function with stdio transport."""
    test_args = ["--transport", "stdio"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run") as mock_asyncio_run,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        mock_asyncio_run.assert_called_once()


def test_main_with_http():
    """Test main function with http transport."""
    test_args = ["--transport", "http"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run") as mock_asyncio_run,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        mock_asyncio_run.assert_called_once()


def test_main_with_debug():
    """Test main function with debug flag."""
    test_args = ["--debug"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run"),
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        # Verify debug was passed to setup_logging
        call_args = mock_setup_logging.call_args
        assert call_args[0][1] is True  # debug parameter


def test_main_with_cody_flag():
    """Test main function with cody flag."""
    test_args = ["--cody"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run") as mock_asyncio_run,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        mock_asyncio_run.assert_called_once()


def test_main_config_file_not_found():
    """Test main function with missing config file."""
    with (
        patch("sys.argv", ["mcp_fess"]),
        patch("mcp_fess.server.load_config", side_effect=FileNotFoundError("Config not found")),
        patch("sys.exit") as mock_exit,
    ):
        main()
        mock_exit.assert_called_once_with(1)


def test_main_invalid_config():
    """Test main function with invalid config."""
    with (
        patch("sys.argv", ["mcp_fess"]),
        patch("mcp_fess.server.load_config", side_effect=ValueError("Invalid config")),
        patch("sys.exit") as mock_exit,
    ):
        main()
        mock_exit.assert_called_once_with(1)


def test_main_keyboard_interrupt():
    """Test main function handles keyboard interrupt."""
    with (
        patch("sys.argv", ["mcp_fess"]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run", side_effect=KeyboardInterrupt()),
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        # Should not raise, just exit gracefully
        main()


def test_main_unexpected_error():
    """Test main function handles unexpected errors."""
    with (
        patch("sys.argv", ["mcp_fess"]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run", side_effect=Exception("Unexpected error")),
        patch("sys.exit") as mock_exit,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        mock_exit.assert_called_once_with(1)


def test_main_non_localhost_bind_rejected():
    """Test main function rejects non-localhost bind without permission."""
    test_args = ["--transport", "http"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("sys.exit") as mock_exit,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "0.0.0.0"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        # sys.exit(1) was called at least once
        mock_exit.assert_called_with(1)


def test_main_non_localhost_bind_allowed():
    """Test main function allows non-localhost bind with permission."""
    test_args = ["--transport", "http"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run") as mock_asyncio_run,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "0.0.0.0"
        mock_config.security.allowNonLocalhostBind = True

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        mock_asyncio_run.assert_called_once()


def test_get_domain_block_without_description(test_config):
    """Test domain block generation without description."""
    test_config.domain.description = None
    server = FessServer(test_config)

    domain_block = server._get_domain_block()

    assert "[Knowledge Domain]" in domain_block
    assert "id: test_domain" in domain_block
    assert "name: Test Domain" in domain_block
    assert "description:" not in domain_block


def test_server_default_label(test_config):
    """Test server uses defaultLabel from config."""
    test_config.defaultLabel = "all"
    server = FessServer(test_config)
    assert server.default_label == "all"


def test_server_default_label_backward_compat(test_config):
    """Test server backward compatibility with labelFilter."""
    test_config.domain.labelFilter = "test_label"
    server = FessServer(test_config)
    # Should use labelFilter when defaultLabel is default
    assert server.default_label == "test_label"


# Tests for fetch_content_chunk tool


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_missing_doc_id(fess_server):
    """Test fetch_content_chunk handler with missing docId."""
    with pytest.raises(ValueError, match="docId parameter is required"):
        await fess_server._handle_fetch_content_chunk({})


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_invalid_offset(fess_server):
    """Test fetch_content_chunk handler with invalid offset."""
    with pytest.raises(ValueError, match="offset must be a non-negative integer, got -1"):
        await fess_server._handle_fetch_content_chunk({"docId": "test", "offset": -1})


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_invalid_length(fess_server):
    """Test fetch_content_chunk handler with invalid length."""
    with pytest.raises(ValueError, match="length must be a positive integer, got 0"):
        await fess_server._handle_fetch_content_chunk({"docId": "test", "offset": 0, "length": 0})


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_first_chunk(fess_server):
    """Test fetch_content_chunk handler for first chunk."""
    test_content = "A" * 2000
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "url": "http://example.com/doc.html", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 0, "length": 1000}
        )
        assert isinstance(result, str)
        assert '"hasMore": true' in result
        assert '"offset": 0' in result
        assert '"length": 1000' in result
        assert '"totalLength": 2000' in result


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_middle_chunk(fess_server):
    """Test fetch_content_chunk handler for middle chunk."""
    test_content = "A" * 3000
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "url": "http://example.com/doc.html", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 1000, "length": 1000}
        )
        assert isinstance(result, str)
        assert '"hasMore": true' in result
        assert '"offset": 1000' in result


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_last_chunk(fess_server):
    """Test fetch_content_chunk handler for last chunk."""
    test_content = "A" * 1500
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "url": "http://example.com/doc.html", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 1000, "length": 1000}
        )
        assert isinstance(result, str)
        assert '"hasMore": false' in result
        assert '"length": 500' in result  # Only 500 bytes remaining


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_exact_end(fess_server):
    """Test fetch_content_chunk handler at exact end of content."""
    test_content = "A" * 1000
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "url": "http://example.com/doc.html", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 0, "length": 1000}
        )
        assert isinstance(result, str)
        assert '"hasMore": false' in result


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_doc_not_found(fess_server):
    """Test fetch_content_chunk handler with non-existent document."""
    mock_search_result = {"data": []}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        with pytest.raises(ValueError, match="Document not found"):
            await fess_server._handle_fetch_content_chunk({"docId": "nonexistent"})


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_no_url(fess_server):
    """Test fetch_content_chunk handler with document without URL but with content."""
    test_content = "A" * 1000
    mock_search_result = {"data": [{"doc_id": "test_doc", "content": test_content}]}

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 0, "length": 500}
        )
        assert isinstance(result, str)
        assert '"length": 500' in result


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_default_length(fess_server):
    """Test fetch_content_chunk handler uses default length from config."""
    test_content = "A" * 2000000  # 2MB content
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "url": "http://example.com/doc.html", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        # Call without explicit length
        result = await fess_server._handle_fetch_content_chunk({"docId": "test_doc", "offset": 0})
        assert isinstance(result, str)
        # Should use maxChunkBytes from config (1048576 = 1MB)
        assert '"length": 1048576' in result


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_exceeds_max_chunk_size(fess_server):
    """Test fetch_content_chunk handler returns error when length exceeds maxChunkBytes."""
    max_chunk = fess_server.config.limits.maxChunkBytes
    with pytest.raises(ValueError, match=f"Requested chunk size {max_chunk + 1} exceeds server limit {max_chunk}."):
        await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 0, "length": max_chunk + 1}
        )


@pytest.mark.asyncio
async def test_handle_fetch_content_chunk_includes_metadata(fess_server):
    """Test fetch_content_chunk response includes metadata with max_chunk_size."""
    test_content = "A" * 500
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_chunk(
            {"docId": "test_doc", "offset": 0, "length": 200}
        )
        parsed = json.loads(result)
        assert "metadata" in parsed
        assert parsed["metadata"]["max_chunk_size"] == fess_server.config.limits.maxChunkBytes


@pytest.mark.asyncio
async def test_handle_fetch_content_by_id_includes_metadata(fess_server):
    """Test fetch_content_by_id response includes metadata with max_chunk_size."""
    test_content = "Hello world"
    mock_search_result = {
        "data": [{"doc_id": "test_doc", "content": test_content}]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        result = await fess_server._handle_fetch_content_by_id({"docId": "test_doc"})
        parsed = json.loads(result)
        assert "metadata" in parsed
        assert parsed["metadata"]["max_chunk_size"] == fess_server.config.limits.maxChunkBytes


@pytest.mark.asyncio
async def test_handle_search_pagesize_exceeds_max(fess_server):
    """Test search handler with pageSize exceeding maxPageSize."""
    with pytest.raises(
        ValueError, match="pageSize must be between 1 and 100"
    ):
        await fess_server._handle_search({"query": "test", "pageSize": 101})


def test_main_with_port_argument():
    """Test main function with --port argument for HTTP transport."""
    test_args = ["--transport", "http", "--port", "8080"]

    with (
        patch("sys.argv", ["mcp_fess", *test_args]),
        patch("mcp_fess.server.load_config") as mock_load_config,
        patch("mcp_fess.server.ensure_log_directory") as mock_log_dir,
        patch("mcp_fess.server.setup_logging") as mock_setup_logging,
        patch("asyncio.run") as mock_asyncio_run,
    ):
        mock_config = MagicMock()
        mock_config.domain.name = "Test"
        mock_config.domain.id = "test"
        mock_config.fessBaseUrl = "http://localhost:8080"
        mock_config.logging.level = "info"
        mock_config.httpTransport.bindAddress = "127.0.0.1"
        mock_config.security.allowNonLocalhostBind = False

        mock_load_config.return_value = mock_config
        mock_log_dir.return_value = MagicMock()
        mock_setup_logging.return_value = (MagicMock(), None)

        main()

        mock_asyncio_run.assert_called_once()


@pytest.mark.asyncio
async def test_run_http_uses_config_path(test_config):
    """Test run_http passes path from config to run_http_async."""
    test_config.httpTransport.port = 3000
    test_config.httpTransport.path = "/mcp"
    server = FessServer(test_config)

    with patch.object(server.mcp, "run_http_async", new=AsyncMock()) as mock_run:
        await server.run_http()
        mock_run.assert_called_once_with(
            host="127.0.0.1",
            port=3000,
            path="/mcp",
            stateless_http=True,
        )


@pytest.mark.asyncio
async def test_run_http_port_override(test_config):
    """Test run_http uses port_override when provided."""
    test_config.httpTransport.port = 3000
    test_config.httpTransport.path = "/mcp"
    server = FessServer(test_config)

    with patch.object(server.mcp, "run_http_async", new=AsyncMock()) as mock_run:
        await server.run_http(port_override=9000)
        mock_run.assert_called_once_with(
            host="127.0.0.1",
            port=9000,
            path="/mcp",
            stateless_http=True,
        )


@pytest.mark.asyncio
async def test_run_http_default_port(test_config):
    """Test run_http defaults to port 3000 when config port is 0."""
    test_config.httpTransport.port = 0
    test_config.httpTransport.path = "/mcp"
    server = FessServer(test_config)

    with patch.object(server.mcp, "run_http_async", new=AsyncMock()) as mock_run:
        await server.run_http()
        mock_run.assert_called_once_with(
            host="127.0.0.1",
            port=3000,
            path="/mcp",
            stateless_http=True,
        )



# --- Tests for snippet functionality ---


@pytest.mark.asyncio
async def test_handle_search_snippets_false_unchanged(fess_server):
    """Test that snippets=False (default) returns unchanged results."""
    mock_result = {"data": [{"doc_id": "abc", "title": "Test"}]}

    with patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_search({"query": "test", "snippets": False})
        parsed = json.loads(result)
        assert "mcp_snippets" not in parsed["data"][0]


@pytest.mark.asyncio
async def test_handle_search_snippets_true_attaches_mcp_snippets(fess_server):
    """Test that snippets=True attaches mcp_snippets to each enriched hit."""
    text_content = "The quick brown fox jumps over the lazy dog"
    mock_result = {"data": [{"doc_id": "abc123", "title": "Test"}]}
    mock_text = text_content

    with (
        patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)),
        patch.object(
            fess_server.fess_client,
            "get_extracted_text_by_doc_id",
            new=AsyncMock(return_value=mock_text),
        ),
    ):
        result = await fess_server._handle_search({"query": "fox", "snippets": True})
        parsed = json.loads(result)
        doc = parsed["data"][0]
        assert "mcp_snippets" in doc
        assert "snippets" in doc["mcp_snippets"]
        assert isinstance(doc["mcp_snippets"]["snippets"], list)
        assert "effective_size_chars" in doc["mcp_snippets"]
        assert "effective_fragments" in doc["mcp_snippets"]
        assert "clamped" in doc["mcp_snippets"]
        assert "source_field" in doc["mcp_snippets"]


@pytest.mark.asyncio
async def test_handle_search_snippets_highlight_applied(fess_server):
    """Test that snippet text contains the highlight markup."""
    mock_result = {"data": [{"doc_id": "abc123", "title": "Test"}]}
    mock_text = "The quick brown fox jumps over the lazy dog"

    with (
        patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)),
        patch.object(
            fess_server.fess_client,
            "get_extracted_text_by_doc_id",
            new=AsyncMock(return_value=mock_text),
        ),
    ):
        result = await fess_server._handle_search({"query": "fox", "snippets": True})
        parsed = json.loads(result)
        snippets_list = parsed["data"][0]["mcp_snippets"]["snippets"]
        combined = " ".join(snippets_list)
        assert "<em>fox</em>" in combined


@pytest.mark.asyncio
async def test_handle_search_snippets_only_first_n_docs_enriched(fess_server):
    """Test that only snippet_docs hits are enriched with snippets."""
    mock_result = {
        "data": [
            {"doc_id": "doc1", "title": "Doc 1"},
            {"doc_id": "doc2", "title": "Doc 2"},
            {"doc_id": "doc3", "title": "Doc 3"},
        ]
    }
    mock_text = "test content with relevant info"

    get_text_mock = AsyncMock(return_value=mock_text)

    with (
        patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)),
        patch.object(
            fess_server.fess_client, "get_extracted_text_by_doc_id", new=get_text_mock
        ),
    ):
        result = await fess_server._handle_search(
            {"query": "test", "snippets": True, "snippet_docs": 2}
        )
        parsed = json.loads(result)
        assert "mcp_snippets" in parsed["data"][0]
        assert "mcp_snippets" in parsed["data"][1]
        assert "mcp_snippets" not in parsed["data"][2]
        # Only 2 fetch calls made
        assert get_text_mock.call_count == 2


@pytest.mark.asyncio
async def test_handle_search_snippets_fetch_error_produces_error_field(fess_server):
    """Test that a fetch error for snippets produces an error field, not an exception."""
    mock_result = {"data": [{"doc_id": "doc1", "title": "Doc 1"}]}

    with (
        patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)),
        patch.object(
            fess_server.fess_client,
            "get_extracted_text_by_doc_id",
            new=AsyncMock(side_effect=ValueError("not found")),
        ),
    ):
        result = await fess_server._handle_search({"query": "test", "snippets": True})
        parsed = json.loads(result)
        assert "mcp_snippets" in parsed["data"][0]
        assert "error" in parsed["data"][0]["mcp_snippets"]


@pytest.mark.asyncio
async def test_handle_search_snippets_clamping(fess_server):
    """Test that snippet params exceeding limits are clamped."""
    mock_result = {"data": [{"doc_id": "doc1", "title": "Doc 1"}]}
    mock_text = "test content"

    with (
        patch.object(fess_server.fess_client, "search", new=AsyncMock(return_value=mock_result)),
        patch.object(
            fess_server.fess_client,
            "get_extracted_text_by_doc_id",
            new=AsyncMock(return_value=mock_text),
        ),
    ):
        result = await fess_server._handle_search(
            {
                "query": "test",
                "snippets": True,
                "snippet_size_chars": 99999,  # exceeds max
                "snippet_fragments": 99,  # exceeds max
            }
        )
        parsed = json.loads(result)
        snippet_meta = parsed["data"][0]["mcp_snippets"]
        assert snippet_meta["clamped"] is True
        limits = fess_server.config.limits
        assert snippet_meta["effective_size_chars"] == limits.snippetMaxChars
        assert snippet_meta["effective_fragments"] == limits.snippetMaxFragments


def test_validate_and_clamp_snippet_args_defaults(fess_server):
    """Test that defaults are applied when no snippet args given."""
    params = fess_server._validate_and_clamp_snippet_args({})
    limits = fess_server.config.limits
    assert params["snippet_size_chars"] == limits.snippetDefaultChars
    assert params["snippet_fragments"] == limits.snippetDefaultFragments
    assert params["snippet_docs"] == limits.snippetDefaultDocs
    assert params["snippet_scan_max_chars"] == limits.snippetScanMaxChars
    assert params["snippet_tag_pre"] == "<em>"
    assert params["snippet_tag_post"] == "</em>"
    assert params["clamped"] is False


def test_validate_and_clamp_snippet_args_clamps_size(fess_server):
    """Test size clamping."""
    limits = fess_server.config.limits
    # Too large
    params = fess_server._validate_and_clamp_snippet_args({"snippet_size_chars": 999999})
    assert params["snippet_size_chars"] == limits.snippetMaxChars
    assert params["clamped"] is True
    # Too small
    params = fess_server._validate_and_clamp_snippet_args({"snippet_size_chars": 1})
    assert params["snippet_size_chars"] == limits.snippetMinChars
    assert params["clamped"] is True


def test_validate_and_clamp_snippet_args_invalid_type(fess_server):
    """Test that invalid types raise ValueError."""
    with pytest.raises(ValueError, match="snippet_size_chars must be a positive integer"):
        fess_server._validate_and_clamp_snippet_args({"snippet_size_chars": "large"})
    with pytest.raises(ValueError, match="snippet_fragments must be a positive integer"):
        fess_server._validate_and_clamp_snippet_args({"snippet_fragments": -1})
    with pytest.raises(ValueError, match="snippet_docs must be a positive integer"):
        fess_server._validate_and_clamp_snippet_args({"snippet_docs": 0})


def test_validate_and_clamp_snippet_args_custom_tags(fess_server):
    """Test custom tags are passed through."""
    params = fess_server._validate_and_clamp_snippet_args(
        {"snippet_tag_pre": "<mark>", "snippet_tag_post": "</mark>"}
    )
    assert params["snippet_tag_pre"] == "<mark>"
    assert params["snippet_tag_post"] == "</mark>"
