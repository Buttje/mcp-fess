"""Top-level FastMCP instance for use with fastmcp run."""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from mcp_fess.config import load_config
from mcp_fess.fess_client import FessClient

logger = logging.getLogger("mcp_fess")

# Module-level state
_server_state: dict[str, Any] = {}


def _get_domain_block() -> str:
    """Generate the Knowledge Domain block for descriptions."""
    config = _server_state["config"]
    domain = config.domain
    desc = f"description: {domain.description}" if domain.description else ""
    return f"""[Knowledge Domain]
id: {domain.id}
name: {domain.name}
{desc}
fessLabel: {domain.labelFilter}"""


def _setup_tools(mcp: FastMCP, domain_id: str) -> None:
    """Set up MCP tools using FastMCP decorators."""

    @mcp.tool(name=f"fess_{domain_id}_search")
    async def search(
        query: str,
        page_size: int = 20,
        start: int = 0,
        sort: str | None = None,
        lang: str | None = None,
        include_fields: list[str] | None = None,
    ) -> str:
        """Search the knowledge domain for documents matching a query."""
        config = _server_state["config"]
        fess_client = _server_state["fess_client"]

        if not query:
            raise ValueError("query parameter is required")

        if not isinstance(page_size, int) or page_size < 1:
            raise ValueError("pageSize must be a positive integer")
        page_size = min(page_size, config.limits.maxPageSize)

        if not isinstance(start, int) or start < 0:
            raise ValueError("start must be a non-negative integer")

        result = await fess_client.search(
            query=query,
            label_filter=config.domain.labelFilter,
            start=start,
            num=page_size,
            sort=sort,
            lang=lang,
        )

        return json.dumps(result, indent=2)

    @mcp.tool(name=f"fess_{domain_id}_suggest")
    async def suggest(
        prefix: str,
        num: int = 10,
        fields: list[str] | None = None,
        lang: str | None = None,
    ) -> str:
        """Suggest related terms for a query in the knowledge domain."""
        config = _server_state["config"]
        fess_client = _server_state["fess_client"]

        if not prefix:
            raise ValueError("prefix parameter is required")

        if not isinstance(num, int) or num < 1:
            raise ValueError("num must be a positive integer")

        result = await fess_client.suggest(
            prefix=prefix,
            label=config.domain.labelFilter,
            num=num,
            fields=fields,
            lang=lang,
        )

        return json.dumps(result, indent=2)

    @mcp.tool(name=f"fess_{domain_id}_popular_words")
    async def popular_words(
        seed: int | None = None,
        field: str | None = None,
    ) -> str:
        """Retrieve popular words in the knowledge domain."""
        config = _server_state["config"]
        fess_client = _server_state["fess_client"]

        result = await fess_client.popular_words(
            label=config.domain.labelFilter, seed=seed, field=field
        )

        return json.dumps(result, indent=2)

    @mcp.tool(name=f"fess_{domain_id}_list_labels")
    async def list_labels() -> str:
        """List all labels configured in the underlying Fess server."""
        fess_client = _server_state["fess_client"]
        result = await fess_client.list_labels()
        return json.dumps(result, indent=2)

    @mcp.tool(name=f"fess_{domain_id}_health")
    async def health() -> str:
        """Check the health status of the underlying Fess server."""
        fess_client = _server_state["fess_client"]
        result = await fess_client.health()
        return json.dumps(result, indent=2)

    @mcp.tool(name=f"fess_{domain_id}_job_get")
    async def job_get(job_id: str) -> str:
        """Retrieve progress information for a long-running operation."""
        if not job_id:
            raise ValueError("jobId parameter is required")

        jobs = _server_state["jobs"]
        if job_id not in jobs:
            return f'{{"error": "Job not found", "jobId": "{job_id}"}}'

        job = jobs[job_id]
        return json.dumps(job, indent=2)


def _setup_resources(mcp: FastMCP, domain_id: str) -> None:
    """Set up MCP resources using FastMCP decorators."""

    @mcp.resource(f"fess://{domain_id}/doc/{{doc_id}}")
    async def read_doc(doc_id: str) -> str:
        """Document metadata."""
        config = _server_state["config"]
        fess_client = _server_state["fess_client"]

        try:
            result = await fess_client.search(
                query=f"doc_id:{doc_id}",
                label_filter=config.domain.labelFilter,
                num=1,
            )

            docs = result.get("data", [])
            if not docs:
                raise ValueError(f"Document not found: {doc_id}")

            doc = docs[0]
            return json.dumps(doc, indent=2)

        except Exception as e:
            logger.error(f"Failed to read resource: {e}")
            raise

    @mcp.resource(f"fess://{domain_id}/doc/{{doc_id}}/content")
    async def read_doc_content(doc_id: str) -> str:
        """Full document content."""
        config = _server_state["config"]
        fess_client = _server_state["fess_client"]

        try:
            result = await fess_client.search(
                query=f"doc_id:{doc_id}",
                label_filter=config.domain.labelFilter,
                num=1,
            )

            docs = result.get("data", [])
            if not docs:
                raise ValueError(f"Document not found: {doc_id}")

            doc = docs[0]
            url = doc.get("url", "")
            if not url:
                raise ValueError("Document has no URL")

            content, _ = await fess_client.fetch_document_content(url, config.contentFetch)

            max_chunk = config.limits.maxChunkBytes
            if len(content) <= max_chunk:
                return str(content)
            else:
                return str(content[:max_chunk])

        except Exception as e:
            logger.error(f"Failed to read resource: {e}")
            raise


@asynccontextmanager
async def lifespan(app: FastMCP) -> Any:
    """Lifespan handler for the FastMCP app."""
    # Startup: Load config and initialize server components
    config = load_config()
    fess_client = FessClient(config.fessBaseUrl, config.timeouts.fessRequestTimeoutMs)

    # Store state for use by tools and resources
    _server_state["config"] = config
    _server_state["fess_client"] = fess_client
    _server_state["jobs"] = {}

    # Setup tools and resources
    domain_id = config.domain.id
    _setup_tools(app, domain_id)
    _setup_resources(app, domain_id)

    logger.info(f"Server components initialized for domain: {domain_id}")

    yield

    # Shutdown: Clean up resources
    await fess_client.close()
    logger.info("Server components cleaned up")


# Create the FastMCP instance at module level
# The name will be updated during lifespan startup based on config
mcp = FastMCP(name="mcp-fess", lifespan=lifespan)
