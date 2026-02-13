"""Tests for the server module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_fess.config import ServerConfig, DomainConfig
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
            labelFilter="test",
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
    assert "fessLabel: test" in domain_block


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
        assert len(result) == 1
        assert "Test" in result[0].text


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

    with patch.object(
        fess_server.fess_client, "suggest", new=AsyncMock(return_value=mock_result)
    ):
        result = await fess_server._handle_suggest({"prefix": "test"})
        assert len(result) == 1
        assert "test1" in result[0].text


@pytest.mark.asyncio
async def test_handle_popular_words_success(fess_server):
    """Test successful popular words."""
    mock_result = {"words": ["word1", "word2"]}

    with patch.object(
        fess_server.fess_client, "popular_words", new=AsyncMock(return_value=mock_result)
    ):
        result = await fess_server._handle_popular_words({})
        assert len(result) == 1
        assert "word1" in result[0].text


@pytest.mark.asyncio
async def test_handle_list_labels_success(fess_server):
    """Test successful list labels."""
    mock_result = {"labels": [{"name": "test"}]}

    with patch.object(
        fess_server.fess_client, "list_labels", new=AsyncMock(return_value=mock_result)
    ):
        result = await fess_server._handle_list_labels()
        assert len(result) == 1
        assert "test" in result[0].text


@pytest.mark.asyncio
async def test_handle_health_success(fess_server):
    """Test successful health check."""
    mock_result = {"status": "green", "timed_out": False}

    with patch.object(fess_server.fess_client, "health", new=AsyncMock(return_value=mock_result)):
        result = await fess_server._handle_health()
        assert len(result) == 1
        assert "green" in result[0].text


@pytest.mark.asyncio
async def test_handle_job_get_missing_job_id(fess_server):
    """Test job get handler with missing job ID."""
    with pytest.raises(ValueError, match="jobId parameter is required"):
        await fess_server._handle_job_get({})


@pytest.mark.asyncio
async def test_handle_job_get_not_found(fess_server):
    """Test job get handler with non-existent job."""
    result = await fess_server._handle_job_get({"jobId": "nonexistent"})
    assert len(result) == 1
    assert "Job not found" in result[0].text


@pytest.mark.asyncio
async def test_handle_job_get_success(fess_server):
    """Test successful job get."""
    fess_server.jobs["test_job"] = {
        "state": "done",
        "progress": 100,
        "message": "Complete",
    }

    result = await fess_server._handle_job_get({"jobId": "test_job"})
    assert len(result) == 1
    assert "done" in result[0].text
    assert "100" in result[0].text


@pytest.mark.asyncio
async def test_cleanup(fess_server):
    """Test server cleanup."""
    with patch.object(fess_server.fess_client, "close", new=AsyncMock()):
        await fess_server.cleanup()
        fess_server.fess_client.close.assert_called_once()

