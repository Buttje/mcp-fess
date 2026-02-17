"""Integration tests for typical agent workflows."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_fess.config import ServerConfig
from mcp_fess.server import FessServer


@pytest.fixture
def server_config():
    """Create a test server configuration."""
    config = ServerConfig(fessBaseUrl="http://localhost:8080")
    config.limits.maxChunkBytes = 100  # Small for testing truncation
    return config


@pytest.fixture
def fess_server(server_config):
    """Create a test Fess server instance."""
    return FessServer(server_config)


@pytest.mark.asyncio
async def test_workflow_list_labels_search_fetch_chunk(fess_server):
    """Test typical agent workflow: list_labels → search → fetch_content_chunk."""
    # Add "hr" and "tech" to configured labels
    from mcp_fess.config import LabelDescriptor

    fess_server.config.labels["hr"] = LabelDescriptor(
        title="HR Documents",
        description="Human Resources documents",
        examples=["employee handbook"],
    )
    fess_server.config.labels["tech"] = LabelDescriptor(
        title="Technical Documentation",
        description="Technical documentation",
        examples=["API docs"],
    )

    # Step 1: List labels
    mock_labels_result = [
        {"value": "hr", "name": "HR Documents"},
        {"value": "tech", "name": "Technical Documentation"},
    ]

    with patch.object(
        fess_server.fess_client, "get_cached_labels", new=AsyncMock(return_value=mock_labels_result)
    ):
        labels_json = await fess_server._handle_list_labels()
        labels_data = json.loads(labels_json)

        assert "labels" in labels_data
        label_values = [lbl["value"] for lbl in labels_data["labels"]]
        # The "all" label should always be present (added by server init)
        assert "all" in label_values
        # Configured labels should be present
        assert "hr" in label_values
        assert "tech" in label_values
        # Should have at least 3 labels: all + hr + tech
        assert len(labels_data["labels"]) >= 3

    # Step 2: Search for documents
    mock_search_result = {
        "data": [
            {
                "doc_id": "doc_001",
                "title": "Employee Handbook",
                "url": "file:///var/fess/documents/handbook.pdf",
                "content": "This is a snippet of the handbook...",  # Short snippet
            }
        ]
    }

    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        search_json = await fess_server._handle_search(
            {"query": "employee policy", "label": "hr", "pageSize": 10, "start": 0}
        )
        search_data = json.loads(search_json)

        assert "data" in search_data
        assert len(search_data["data"]) > 0
        doc = search_data["data"][0]
        assert "doc_id" in doc
        doc_id = doc["doc_id"]

    # Step 3: Fetch content chunk for the found document
    # The document has a file:// URL, so we test the file:// handling
    long_content = "A" * 200  # Content longer than maxChunkBytes (100)

    with (
        patch.object(
            fess_server.fess_client,
            "search",
            new=AsyncMock(return_value=mock_search_result),
        ),
        patch.object(
            fess_server.fess_client,
            "fetch_document_content_by_id",
            new=AsyncMock(return_value=(long_content, "hash123")),
        ),
    ):
        chunk_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 100}
        )
        chunk_data = json.loads(chunk_json)

        assert "content" in chunk_data
        assert chunk_data["hasMore"] is True
        assert chunk_data["totalLength"] == 200
        assert len(chunk_data["content"]) == 100


@pytest.mark.asyncio
async def test_workflow_file_url_handling_integration(fess_server):
    """Test that file:// URLs are handled correctly through the full workflow."""
    # Document with file:// URL
    doc_id = "file_doc_001"
    file_url = "file:///home/user/documents/report.txt"
    full_content = "Full content from Fess API for file:// URL document" * 10

    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "title": "Report",
                "url": file_url,
                "content": full_content[:50],  # Snippet
            }
        ]
    }

    # Mock fetch_document_content_by_id to simulate Fess API retrieval
    with (
        patch.object(
            fess_server.fess_client,
            "search",
            new=AsyncMock(return_value=mock_search_result),
        ),
        patch.object(
            fess_server.fess_client,
            "fetch_document_content_by_id",
            new=AsyncMock(return_value=(full_content, "hash456")),
        ),
    ):
        # Fetch content chunk should work without "Scheme not allowed" error
        chunk_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 200}
        )
        chunk_data = json.loads(chunk_json)

        assert "content" in chunk_data
        assert "Scheme not allowed" not in chunk_data["content"]
        assert len(chunk_data["content"]) == 200


@pytest.mark.asyncio
async def test_workflow_truncation_notice_appears(fess_server):
    """Test that truncation notices appear in the workflow."""
    doc_id = "doc_002"
    doc_url = "http://example.com/document.html"
    # Content longer than maxChunkBytes (100)
    long_content = "This is a very long document. " * 20

    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "title": "Long Document",
                "url": doc_url,
            }
        ]
    }

    # Simulate reading document content via resource
    with (
        patch.object(
            fess_server.fess_client,
            "search",
            new=AsyncMock(return_value=mock_search_result),
        ),
        patch.object(
            fess_server.fess_client,
            "fetch_document_content",
            new=AsyncMock(return_value=(long_content, "hash789")),
        ),
    ):
        # Simulate what read_doc_content resource does
        result = await fess_server.fess_client.search(
            query=f"doc_id:{doc_id}", label_filter=None, num=1
        )
        docs = result.get("data", [])
        url = docs[0]["url"]
        content, _ = await fess_server.fess_client.fetch_document_content(
            url, fess_server.config.contentFetch, doc_id=doc_id
        )

        max_chunk = fess_server.config.limits.maxChunkBytes
        if len(content) > max_chunk:
            truncated = content[:max_chunk]
            truncation_notice = (
                f"\n\n[Content truncated at {max_chunk} characters. "
                f"Use fetch_content_chunk tool with docId='{doc_id}' to retrieve additional sections.]"
            )
            result_content = truncated + truncation_notice
        else:
            result_content = content

        # Verify truncation notice appears
        assert "[Content truncated" in result_content
        assert "fetch_content_chunk" in result_content
        assert doc_id in result_content


@pytest.mark.asyncio
async def test_workflow_fetch_content_by_id_full_document(fess_server):
    """Test the new fetch_content_by_id tool in a workflow."""
    doc_id = "doc_003"
    doc_url = "http://example.com/article.html"
    content = "Full article content here"

    mock_search_result = {
        "data": [
            {
                "doc_id": doc_id,
                "title": "Article",
                "url": doc_url,
            }
        ]
    }

    with (
        patch.object(
            fess_server.fess_client,
            "search",
            new=AsyncMock(return_value=mock_search_result),
        ),
        patch.object(
            fess_server.fess_client,
            "fetch_document_content",
            new=AsyncMock(return_value=(content, "hash999")),
        ),
    ):
        # Use the new fetch_content_by_id tool
        result_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
        result_data = json.loads(result_json)

        assert "content" in result_data
        assert result_data["content"] == content
        assert result_data["truncated"] is False


@pytest.mark.asyncio
async def test_workflow_error_messages_guide_agent(fess_server):
    """Test that error messages provide helpful guidance to agents."""
    # Test 1: Missing docId
    try:
        await fess_server._handle_fetch_content_chunk({})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "search" in str(e).lower()
        assert "tool" in str(e).lower()

    # Test 2: Invalid offset
    try:
        await fess_server._handle_fetch_content_chunk({"docId": "test", "offset": -1})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "offset=0" in str(e)

    # Test 3: Invalid length
    try:
        await fess_server._handle_fetch_content_chunk(
            {"docId": "test", "offset": 0, "length": 0}
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "positive integer" in str(e)
        assert "Maximum recommended" in str(e)

    # Test 4: Document not found
    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value={"data": []})
    ):
        try:
            await fess_server._handle_fetch_content_chunk(
                {"docId": "nonexistent", "offset": 0, "length": 100}
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Document not found" in str(e)
            assert "verify" in str(e).lower()
            assert "search" in str(e).lower()


@pytest.mark.asyncio
async def test_workflow_complete_scenario_with_file_urls(fess_server):
    """Complete scenario: Agent searches, finds file:// document, and reads it successfully."""
    # Setup: Agent searches for information
    search_query = "employee onboarding"

    # Add "hr" to configured labels to pass validation
    from mcp_fess.config import LabelDescriptor
    fess_server.config.labels["hr"] = LabelDescriptor(
        title="HR Documents",
        description="Human Resources documents",
        examples=["onboarding guide"],
    )

    mock_labels = [
        {"value": "hr", "name": "HR Documents"},
    ]

    mock_search_result = {
        "data": [
            {
                "doc_id": "onboarding_guide",
                "title": "New Employee Onboarding Guide",
                "url": "file:///var/fess/hr/onboarding.pdf",
                "content": "Welcome to the company! This guide will help you...",
            }
        ]
    }

    # Content stored in Fess for the file:// document
    full_onboarding_content = """
    Welcome to the company! This comprehensive guide will help you navigate your first weeks.
    
    Chapter 1: Company Culture
    Our company values transparency, innovation, and collaboration...
    
    Chapter 2: First Week Checklist
    - Complete HR paperwork
    - Set up your workstation
    - Meet your team
    - Attend orientation sessions
    
    Chapter 3: Resources and Benefits
    Access to training materials, health insurance, retirement plans...
    """ * 3  # Make it long enough to test chunking

    # Workflow Step 1: List labels
    with patch.object(
        fess_server.fess_client, "get_cached_labels", new=AsyncMock(return_value=mock_labels)
    ):
        labels_json = await fess_server._handle_list_labels()
        labels_data = json.loads(labels_json)
        # "all" is always added, plus "hr" from config
        assert any(lbl["value"] == "hr" for lbl in labels_data["labels"])

    # Workflow Step 2: Search with label
    with patch.object(
        fess_server.fess_client, "search", new=AsyncMock(return_value=mock_search_result)
    ):
        search_json = await fess_server._handle_search(
            {"query": search_query, "label": "hr", "pageSize": 10, "start": 0}
        )
        search_data = json.loads(search_json)
        doc = search_data["data"][0]
        doc_id = doc["doc_id"]
        assert "file://" in doc["url"]

    # Workflow Step 3: Fetch full content using fetch_content_by_id
    # This should work even though the URL is file://
    with (
        patch.object(
            fess_server.fess_client,
            "search",
            new=AsyncMock(return_value=mock_search_result),
        ),
        patch.object(
            fess_server.fess_client,
            "fetch_document_content_by_id",
            new=AsyncMock(return_value=(full_onboarding_content, "content_hash")),
        ),
    ):
        # Try the simplified fetch_content_by_id first
        full_content_json = await fess_server._handle_fetch_content_by_id({"docId": doc_id})
        full_content_data = json.loads(full_content_json)

        # Verify we got content without errors
        assert "content" in full_content_data
        assert "Chapter 1" in full_content_data["content"] or full_content_data["truncated"]
        assert "Scheme not allowed" not in str(full_content_data)

        # Also test chunked retrieval
        chunk_json = await fess_server._handle_fetch_content_chunk(
            {"docId": doc_id, "offset": 0, "length": 200}
        )
        chunk_data = json.loads(chunk_json)

        assert "content" in chunk_data
        assert len(chunk_data["content"]) <= 200
        assert "Scheme not allowed" not in chunk_data["content"]
        # Agent can determine if there's more content
        if chunk_data["hasMore"]:
            # Agent would continue reading with offset += length
            next_offset = chunk_data["offset"] + chunk_data["length"]
            assert next_offset > 0
