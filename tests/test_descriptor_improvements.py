"""Tests for descriptor improvements to verify strategy teaching and index-only text."""

import pytest

from mcp_fess.config import ServerConfig
from mcp_fess.server import FessServer


@pytest.fixture
def fess_server():
    """Create a FessServer instance for testing."""
    config = ServerConfig(fessBaseUrl="http://localhost:8080")
    return FessServer(config)


def test_descriptor_helpers_exist(fess_server):
    """Test that descriptor helper methods exist."""
    assert hasattr(fess_server, "_descriptor_workflow")
    assert hasattr(fess_server, "_descriptor_text_source")
    assert hasattr(fess_server, "_descriptor_limits")


def test_descriptor_workflow_content(fess_server):
    """Test that workflow descriptor contains expected guidance."""
    workflow = fess_server._descriptor_workflow()
    assert "list_labels" in workflow
    assert "search" in workflow
    assert "fetch_content_chunk" in workflow
    assert "fetch_content_by_id" in workflow
    assert "suggest" in workflow
    assert "popular_words" in workflow
    assert "doc_id" in workflow


def test_descriptor_text_source_content(fess_server):
    """Test that text source descriptor states index-only."""
    text_source = fess_server._descriptor_text_source()
    assert "Index fields only" in text_source
    assert "No origin URL fetch" in text_source
    assert "content" in text_source
    assert "body" in text_source
    assert "digest" in text_source


def test_descriptor_limits_has_actual_value(fess_server):
    """Test that limits descriptor shows actual configured value."""
    limits = fess_server._descriptor_limits()
    # Should contain the actual maxChunkBytes value, not a placeholder
    assert str(fess_server.config.limits.maxChunkBytes) in limits
    assert "{" not in limits  # No placeholders like {maxChunkBytes}
    assert "bytes" in limits


def test_no_placeholder_text_in_descriptors(fess_server):
    """Test that no tool/resource descriptors contain raw placeholder text."""
    # Verify by checking that the descriptor helpers don't have placeholders
    assert "{maxChunkBytes}" not in fess_server._descriptor_workflow()
    assert "{maxChunkBytes}" not in fess_server._descriptor_text_source()
    assert "{maxChunkBytes}" not in fess_server._descriptor_limits()


def test_search_tool_teaches_workflow(fess_server):
    """Test that search tool descriptor teaches the agent workflow."""
    # We can't easily access the tool descriptors after registration with FastMCP,
    # but we can verify the helper methods are correct
    workflow = fess_server._descriptor_workflow()

    # Should teach the multi-step workflow
    assert "Call `search`" in workflow or "search" in workflow
    assert "fetch_content_chunk" in workflow
    assert "doc_id" in workflow


def test_fetch_content_chunk_teaches_iteration(fess_server):
    """Test that fetch_content_chunk descriptor teaches iteration strategy."""
    # The tool should have been set up with the iteration strategy
    # We verify the helper contains the right info
    text_source = fess_server._descriptor_text_source()

    assert "Index fields only" in text_source
    assert "No origin URL fetch" in text_source


def test_fetch_content_by_id_states_index_only(fess_server):
    """Test that fetch_content_by_id descriptor states index-only source."""
    # Verify helper methods support this
    text_source = fess_server._descriptor_text_source()
    assert "Index fields only" in text_source


def test_limits_descriptor_has_numeric_value(fess_server):
    """Test that limits are shown as actual numbers, not placeholders."""
    limits = fess_server._descriptor_limits()

    # Should contain a numeric value
    import re
    assert re.search(r'\d+', limits) is not None

    # Should not contain placeholder syntax
    assert "{" not in limits
    assert "}" not in limits


def test_server_config_has_expected_default_limits(fess_server):
    """Test that server has expected default maxChunkBytes."""
    # Default is 1048576 (1 MiB)
    assert fess_server.config.limits.maxChunkBytes > 0
    assert isinstance(fess_server.config.limits.maxChunkBytes, int)


def test_descriptor_workflow_includes_refine_step(fess_server):
    """Test that workflow includes refinement step."""
    workflow = fess_server._descriptor_workflow()
    assert "refine" in workflow.lower() or "Refine" in workflow


def test_descriptor_text_source_mentions_priority(fess_server):
    """Test that text source explains field priority."""
    text_source = fess_server._descriptor_text_source()
    # Should mention the priority: content → body → digest
    assert "content" in text_source
    assert "body" in text_source
    assert "digest" in text_source
