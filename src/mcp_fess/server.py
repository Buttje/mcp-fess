"""MCP Server for Fess."""

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from fastmcp import FastMCP

from .config import ServerConfig, ensure_log_directory, load_config
from .fess_client import FessClient
from .logging_utils import setup_logging

logger = logging.getLogger("mcp_fess")


class FessServer:
    """MCP server implementation for Fess."""

    def __init__(self, config: ServerConfig, protocol_version: str = "2025-03-26") -> None:
        self.config = config
        self.protocol_version = protocol_version
        self.fess_client = FessClient(config.fessBaseUrl, config.timeouts.fessRequestTimeoutMs)

        server_name = f"mcp-fess-{config.domain.id}"
        self.mcp = FastMCP(name=server_name)
        self.domain_id = config.domain.id
        self.jobs: dict[str, dict[str, Any]] = {}
        self.default_label = config.get_effective_default_label()

        # Ensure "all" label is always in config
        if "all" not in self.config.labels:
            from .config import LabelDescriptor

            self.config.labels["all"] = LabelDescriptor(
                title="All documents",
                description="Search across the whole Fess index without label filtering.",
                examples=["company policy", "project documentation"],
            )

        self._setup_tools()
        self._setup_resources()

    def _get_domain_block(self) -> str:
        """Generate the Knowledge Domain block for descriptions."""
        domain = self.config.domain
        desc = f"description: {domain.description}" if domain.description else ""
        return f"""[Knowledge Domain]
id: {domain.id}
name: {domain.name}
{desc}
fessLabel: {domain.labelFilter}"""

    def _descriptor_workflow(self) -> str:
        """Generate the shared efficient agent workflow text."""
        return """**Efficient agent workflow:**

1. (Optional) Call `list_labels` to pick a label scope if you need to restrict the search space.
2. Call `search` to get relevant hits and collect `doc_id`s.
3. Call `fetch_content_chunk` (preferred) or `fetch_content_by_id` to read extracted UTF-8 text evidence from the index.
4. Refine the query using evidence; optionally use `suggest` and `popular_words` to expand/pivot."""

    def _descriptor_text_source(self) -> str:
        """Generate the text source explanation."""
        return "**Text source:** Index fields only (priority: `content` → `body` → `digest`). No origin URL fetch."

    def _descriptor_limits(self) -> str:
        """Generate the limits description with actual configured values."""
        return f"**Maximum chunk size:** {self.config.limits.maxChunkBytes} bytes."

    def _setup_tools(self) -> None:
        """Set up MCP tools using FastMCP decorators."""

        @self.mcp.tool(name=f"fess_{self.domain_id}_search")
        async def search(
            query: str,
            label: str | None = None,
            page_size: int = 20,
            start: int = 0,
            sort: str | None = None,
            lang: str | None = None,
            include_fields: list[str] | None = None,
        ) -> str:
            return await self._handle_search(
                {
                    "query": query,
                    "label": label,
                    "pageSize": page_size,
                    "start": start,
                    "sort": sort,
                    "lang": lang,
                    "includeFields": include_fields,
                }
            )

        # Set dynamic descriptor for search tool
        search.__doc__ = f"""Search the Fess index and return ranked document hits.
Use this first to turn a keyword/question into a shortlist of candidate documents (capture `doc_id`).

{self._descriptor_workflow()}

**Note:** Search hits may include only short summary/snippet fields. For substantial text evidence, always use the content fetch tool/resource.

**Performance:** Use `include_fields` to limit payload to the fields you need.

Args:
    query: Search term
    label: Label value to scope the search (default uses configured defaultLabel).
           Use 'all' to search across the entire index without label filtering.
           Call list_labels to see available labels.
    page_size: Number of results per page (default 20, max 100)
    start: Starting index for pagination (default 0)
    sort: Sort order
    lang: Search language
    include_fields: Fields to include in results"""

        @self.mcp.tool(name=f"fess_{self.domain_id}_suggest")
        async def suggest(
            prefix: str,
            num: int = 10,
            fields: list[str] | None = None,
            lang: str | None = None,
        ) -> str:
            return await self._handle_suggest(
                {
                    "prefix": prefix,
                    "num": num,
                    "fields": fields,
                    "lang": lang,
                }
            )

        # Set dynamic descriptor for suggest tool
        suggest.__doc__ = """Get query suggestions based on the index vocabulary.
Use after reviewing evidence to generate grounded query expansions (synonyms, prefixes, near-terms).

Args:
    prefix: Search prefix for suggestions
    num: Number of suggestions to return (default 10)
    fields: Fields to search for suggestions
    lang: Search language"""

        @self.mcp.tool(name=f"fess_{self.domain_id}_popular_words")
        async def popular_words(
            seed: int | None = None,
            field: str | None = None,
        ) -> str:
            return await self._handle_popular_words(
                {
                    "seed": seed,
                    "field": field,
                }
            )

        # Set dynamic descriptor for popular_words tool
        popular_words.__doc__ = """Get popular words/terms from the index.
Use to discover dominant vocabulary for pivots, filters, and follow-up query formulation.

Args:
    seed: Random seed for word selection
    field: Field to extract popular words from"""

        @self.mcp.tool(name=f"fess_{self.domain_id}_list_labels")
        async def list_labels() -> str:
            return await self._handle_list_labels()

        # Set dynamic descriptor for list_labels tool
        list_labels.__doc__ = """List available label scopes, including descriptions/examples when configured and whether each label exists in Fess.
Use this at the start when query intent is unclear or you need a constrained search scope.

Returns label values with descriptions, examples, and availability status."""

        @self.mcp.tool(name=f"fess_{self.domain_id}_health")
        async def health() -> str:
            return await self._handle_health()

        # Set dynamic descriptor for health tool
        health.__doc__ = """Check the health status of the underlying Fess server."""

        @self.mcp.tool(name=f"fess_{self.domain_id}_job_get")
        async def job_get(job_id: str) -> str:
            return await self._handle_job_get({"jobId": job_id})

        # Set dynamic descriptor for job_get tool
        job_get.__doc__ = """Retrieve progress information for a long-running operation.

Args:
    job_id: The job ID to query"""

        @self.mcp.tool(name=f"fess_{self.domain_id}_fetch_content_by_id")
        async def fetch_content_by_id(doc_id: str) -> str:
            return await self._handle_fetch_content_by_id({"docId": doc_id})

        # Set dynamic descriptor for fetch_content_by_id tool
        fetch_content_by_id.__doc__ = f"""Fetch extracted UTF-8 text for a document from the Fess index in one call (no origin URL fetch).

Use when the document is expected to fit within the server's maximum chunk limit or when you want a quick read without managing offsets.
If the document exceeds the limit, content is truncated; use `fetch_content_chunk` for full traversal.

{self._descriptor_text_source()}
{self._descriptor_limits()}

Args:
    doc_id: Document ID obtained from search results (required)

Returns:
    JSON with:
    - 'content': The document content (up to maximum chunk size)
    - 'totalLength': Total document length in characters
    - 'truncated': Boolean indicating if content was truncated due to size limits"""

        @self.mcp.tool(name=f"fess_{self.domain_id}_fetch_content_chunk")
        async def fetch_content_chunk(
            doc_id: str,
            offset: int = 0,
            length: int | None = None,
        ) -> str:
            if length is None:
                length = self.config.limits.maxChunkBytes
            return await self._handle_fetch_content_chunk(
                {"docId": doc_id, "offset": offset, "length": length}
            )

        # Set dynamic descriptor for fetch_content_chunk tool
        fetch_content_chunk.__doc__ = f"""Fetch a window of extracted UTF-8 text for a document from the Fess index (no origin URL fetch).

Use this after `search` when you need substantial evidence (sections/chapters/whole documents).

**Chunking strategy:**

* Start with `offset=0`.
* Request a `length` up to the server's maximum chunk limit.
* If `hasMore=true`, set `offset = offset + returned_length` and call again.
* Repeat until `hasMore=false`.

{self._descriptor_text_source()}
{self._descriptor_limits()}

Args:
    doc_id: Document ID obtained from search results (required)
    offset: Character offset into document (default 0 - start from beginning)
    length: Number of characters to return (default maximum chunk size)

Returns:
    JSON with:
    - 'content': The requested text chunk
    - 'hasMore': Boolean indicating if more content exists beyond this chunk
    - 'offset': The starting position of this chunk
    - 'length': Actual length of returned content
    - 'totalLength': Total document length in characters"""

    def _setup_resources(self) -> None:
        """Set up MCP resources using FastMCP decorators."""

        @self.mcp.resource(f"fess://{self.domain_id}/doc/{{doc_id}}")
        async def read_doc(doc_id: str) -> str:
            try:
                # Use default label if it's not "all"
                label_filter = None if self.default_label == "all" else self.default_label

                result = await self.fess_client.search(
                    query=f"doc_id:{doc_id}",
                    label_filter=label_filter,
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

        # Set dynamic descriptor for read_doc resource
        read_doc.__doc__ = """Document metadata for a given `doc_id`.
Use `doc/{doc_id}/content` or the content fetch tools to retrieve extracted text."""

        @self.mcp.resource(f"fess://{self.domain_id}/doc/{{doc_id}}/content")
        async def read_doc_content(doc_id: str) -> str:
            try:
                # Use default label if it's not "all"
                label_filter = None if self.default_label == "all" else self.default_label

                # Get extracted text from Fess index only
                from .fess_client import truncate_text_utf8_safe

                content = await self.fess_client.get_extracted_text_by_doc_id(
                    doc_id, label_filter=label_filter
                )

                max_chunk = self.config.limits.maxChunkBytes
                truncated_content, was_truncated = truncate_text_utf8_safe(content, max_chunk)

                if was_truncated:
                    # Add truncation notice to help agents understand content is incomplete
                    truncation_notice = (
                        f"\n\n[Content truncated at {max_chunk} bytes. "
                        f"Use fetch_content_chunk tool with docId='{doc_id}' to retrieve additional sections.]"
                    )
                    return truncated_content + truncation_notice
                else:
                    return truncated_content

            except Exception as e:
                logger.error(f"Failed to read resource: {e}")
                raise

        # Set dynamic descriptor for read_doc_content resource
        read_doc_content.__doc__ = f"""Document extracted text (index-only). Returns up to the server's maximum chunk limit.
For longer documents, use `fetch_content_chunk` to iterate through the full extracted text.

{self._descriptor_limits()}"""

        @self.mcp.resource(f"fess://{self.domain_id}/labels")
        async def read_labels() -> str:
            return await self._handle_list_labels()

        # Set dynamic descriptor for read_labels resource
        read_labels.__doc__ = """Available Fess labels with descriptions."""

    async def _validate_label(self, label: str) -> None:
        """Validate that a label is allowed.

        Args:
            label: Label to validate

        Raises:
            ValueError: If label is invalid in strict mode
        """
        if label == "all":
            return  # "all" is always allowed

        # Check if label is in config
        if label in self.config.labels:
            return

        # Check if label exists in Fess
        try:
            fess_labels = await self.fess_client.get_cached_labels()
            fess_label_values = {lbl.get("value") for lbl in fess_labels if lbl.get("value")}

            if label in fess_label_values:
                if self.config.strictLabels:
                    logger.warning(
                        f"Label '{label}' exists in Fess but not in config. "
                        "Consider adding it to the labels configuration."
                    )
                return
        except Exception as e:
            logger.warning(f"Failed to validate label against Fess: {e}")

        # Label not found
        if self.config.strictLabels:
            raise ValueError(
                f"Unknown label '{label}'. Call list_labels to see available labels."
            )
        else:
            logger.warning(
                f"Label '{label}' is not configured and may not exist in Fess. "
                "Proceeding anyway (strictLabels=false)."
            )

    async def _handle_search(self, arguments: dict[str, Any]) -> str:
        """Handle search tool."""
        logger.debug(f"MCP tool call: search args={arguments}")
        query = arguments.get("query")
        if not query:
            raise ValueError("query parameter is required")

        page_size = arguments.get("pageSize", 20)
        if not isinstance(page_size, int) or page_size < 1:
            raise ValueError("pageSize must be a positive integer")
        if page_size > self.config.limits.maxPageSize:
            raise ValueError(
                f"pageSize must be between 1 and {self.config.limits.maxPageSize}, "
                f"got {page_size}"
            )

        start = arguments.get("start", 0)
        if not isinstance(start, int) or start < 0:
            raise ValueError("start must be a non-negative integer")

        # Determine effective label
        label = arguments.get("label")
        if label is None:
            label = self.default_label

        # Validate label type
        if not isinstance(label, str):
            raise ValueError("label must be a string")

        # Validate label value
        await self._validate_label(label)

        sort = arguments.get("sort")
        lang = arguments.get("lang")

        # Map label to Fess query parameter
        label_filter = None if label == "all" else label

        result = await self.fess_client.search(
            query=query,
            label_filter=label_filter,
            start=start,
            num=page_size,
            sort=sort,
            lang=lang,
        )

        # Remove Solr internal _id from each document to avoid agent misinterpretation
        for doc in result.get("data", []):
            doc.pop("_id", None)

        response = json.dumps(result, indent=2)
        logger.debug(
            f"MCP tool response: search hits={result.get('record_count', len(result.get('data', [])))}"
        )
        return response

    async def _handle_suggest(self, arguments: dict[str, Any]) -> str:
        """Handle suggest tool."""
        logger.debug(f"MCP tool call: suggest args={arguments}")
        prefix = arguments.get("prefix")
        if not prefix:
            raise ValueError("prefix parameter is required")

        num = arguments.get("num", 10)
        if not isinstance(num, int) or num < 1:
            raise ValueError("num must be a positive integer")

        fields = arguments.get("fields")
        lang = arguments.get("lang")

        # Use default label if it's not "all"
        label = None if self.default_label == "all" else self.default_label

        result = await self.fess_client.suggest(
            prefix=prefix,
            label=label,
            num=num,
            fields=fields,
            lang=lang,
        )

        response = json.dumps(result, indent=2)
        logger.debug(f"MCP tool response: suggest count={len(result.get('data', []))}")
        return response

    async def _handle_popular_words(self, arguments: dict[str, Any]) -> str:
        """Handle popular words tool."""
        logger.debug(f"MCP tool call: popular_words args={arguments}")
        seed = arguments.get("seed")
        field = arguments.get("field")

        # Use default label if it's not "all"
        label = None if self.default_label == "all" else self.default_label

        result = await self.fess_client.popular_words(label=label, seed=seed, field=field)

        response = json.dumps(result, indent=2)
        logger.debug(f"MCP tool response: popular_words count={len(result.get('data', []))}")
        return response

    async def _handle_list_labels(self) -> str:
        """Handle list labels tool.

        Returns merged catalog of labels from config and Fess with descriptions.
        """
        logger.debug("MCP tool call: list_labels")
        # Get labels from Fess
        fess_labels_available = True
        try:
            fess_labels = await self.fess_client.get_cached_labels()
            fess_label_map: dict[str, str] = {
                lbl.get("value", ""): lbl.get("name", "") for lbl in fess_labels if lbl.get("value")
            }
        except Exception as e:
            logger.warning(f"Failed to fetch labels from Fess: {e}")
            fess_labels_available = False
            fess_label_map = {}

        # Merge with config
        merged_labels = []

        # Add all configured labels
        for value, descriptor in self.config.labels.items():
            merged_labels.append(
                {
                    "value": value,
                    "name": fess_label_map.get(value, ""),
                    "title": descriptor.title,
                    "description": descriptor.description,
                    "examples": descriptor.examples,
                    "isConfigured": True,
                    "isPresentInFess": value in fess_label_map or value == "all",
                }
            )

        # Add unconfigured labels from Fess
        if not self.config.strictLabels:
            for value, name in fess_label_map.items():
                if value not in self.config.labels:
                    merged_labels.append(
                        {
                            "value": value,
                            "name": name,
                            "title": name or value,
                            "description": "No description configured.",
                            "examples": [],
                            "isConfigured": False,
                            "isPresentInFess": True,
                        }
                    )

        result = {
            "labels": merged_labels,
            "defaultLabel": self.default_label,
            "strictLabels": self.config.strictLabels,
            "fessAvailable": fess_labels_available,
        }

        response = json.dumps(result, indent=2)
        logger.debug(f"MCP tool response: list_labels count={len(merged_labels)}")
        return response

    async def _handle_health(self) -> str:
        """Handle health check tool."""
        logger.debug("MCP tool call: health")
        result = await self.fess_client.health()

        response = json.dumps(result, indent=2)
        logger.debug(f"MCP tool response: health status={result.get('status', 'unknown')}")
        return response

    async def _handle_job_get(self, arguments: dict[str, Any]) -> str:
        """Handle job status query."""
        logger.debug(f"MCP tool call: job_get args={arguments}")
        job_id = arguments.get("jobId")
        if not job_id:
            raise ValueError("jobId parameter is required")

        if job_id not in self.jobs:
            return f'{{"error": "Job not found", "jobId": "{job_id}"}}'

        job = self.jobs[job_id]

        return json.dumps(job, indent=2)

    async def _handle_fetch_content_chunk(self, arguments: dict[str, Any]) -> str:
        """Handle fetch content chunk tool."""
        logger.debug(f"MCP tool call: fetch_content_chunk args={arguments}")
        doc_id = arguments.get("docId")
        if not doc_id:
            raise ValueError(
                "docId parameter is required. "
                "Please use the 'search' tool first to obtain a valid document ID."
            )

        offset = arguments.get("offset", 0)
        if not isinstance(offset, int) or offset < 0:
            raise ValueError(
                f"offset must be a non-negative integer, got {offset}. "
                "Use offset=0 to start reading from the beginning."
            )

        length = arguments.get("length", self.config.limits.maxChunkBytes)
        if not isinstance(length, int) or length < 1:
            raise ValueError(
                f"length must be a positive integer, got {length}. "
                f"Maximum recommended length is {self.config.limits.maxChunkBytes} bytes."
            )

        # Enforce maxChunkBytes limit on length
        max_chunk_bytes = self.config.limits.maxChunkBytes
        if length > max_chunk_bytes:
            length = max_chunk_bytes
            logger.debug(
                f"Requested length {arguments.get('length')} exceeds maxChunkBytes, "
                f"capping at {max_chunk_bytes}"
            )

        try:
            # Use default label if it's not "all"
            label_filter = None if self.default_label == "all" else self.default_label

            # Get full extracted text from Fess index
            content = await self.fess_client.get_extracted_text_by_doc_id(
                doc_id, label_filter=label_filter
            )

            # Slice content at character level
            chunk = content[offset : offset + length]
            has_more = offset + length < len(content)

            result = {
                "content": chunk,
                "hasMore": has_more,
                "offset": offset,
                "length": len(chunk),
                "totalLength": len(content),
            }

            response = json.dumps(result, indent=2)
            logger.debug(
                f"MCP tool response: fetch_content_chunk doc_id={doc_id} "
                f"offset={offset} length={len(chunk)} hasMore={has_more} totalLength={len(content)}"
            )
            return response

        except ValueError:
            # Re-raise ValueError with improved context
            raise
        except Exception as e:
            # Catch any other errors and provide helpful message
            logger.error(f"Failed to fetch content chunk for {doc_id}: {e}")
            raise ValueError(
                f"fetch_content_chunk failed to load document {doc_id}. "
                f"Error: {e!s}. Please verify the document ID using 'search' tool, "
                "or check offset/length parameters."
            ) from e

    async def _handle_fetch_content_by_id(self, arguments: dict[str, Any]) -> str:
        """Handle fetch content by ID tool."""
        logger.debug(f"MCP tool call: fetch_content_by_id args={arguments}")
        doc_id = arguments.get("docId")
        if not doc_id:
            raise ValueError(
                "docId parameter is required. "
                "Please use the 'search' tool first to obtain a valid document ID."
            )

        try:
            # Use default label if it's not "all"
            label_filter = None if self.default_label == "all" else self.default_label

            # Get full extracted text from Fess index
            content = await self.fess_client.get_extracted_text_by_doc_id(
                doc_id, label_filter=label_filter
            )

            # Store original length before truncation
            original_length = len(content)

            # Check if content exceeds maxChunkBytes limit
            from .fess_client import truncate_text_utf8_safe

            max_bytes = self.config.limits.maxChunkBytes
            truncated_content, was_truncated = truncate_text_utf8_safe(content, max_bytes)

            result = {
                "content": truncated_content,
                "totalLength": original_length,  # Full document length
                "truncated": was_truncated,
            }

            if was_truncated:
                result["message"] = (
                    f"Content was truncated at {max_bytes} bytes. "
                    f"Full document is {original_length} characters. "
                    f"Use fetch_content_chunk tool with docId='{doc_id}' "
                    "to retrieve additional sections."
                )

            response = json.dumps(result, indent=2)
            logger.debug(
                f"MCP tool response: fetch_content_by_id doc_id={doc_id} "
                f"totalLength={original_length} truncated={was_truncated}"
            )
            return response

        except ValueError:
            # Re-raise ValueError with improved context
            raise
        except Exception as e:
            # Catch any other errors and provide helpful message
            logger.error(f"Failed to fetch content by ID for {doc_id}: {e}")
            raise ValueError(
                f"fetch_content_by_id failed to load document {doc_id}. "
                f"Error: {e!s}. Please verify the document ID using 'search' tool."
            ) from e

    async def run_stdio(self) -> None:
        """Run server with stdio transport."""
        await self.mcp.run_stdio_async()

    async def run_http(self, port_override: int | None = None) -> None:
        """Run server with HTTP transport."""
        bind_addr = self.config.httpTransport.bindAddress
        port = port_override if port_override is not None else self.config.httpTransport.port
        if port == 0:
            port = 3000

        path = self.config.httpTransport.path
        logger.info(f"Starting HTTP server on {bind_addr}:{port}{path}")

        await self.mcp.run_http_async(host=bind_addr, port=port, path=path, stateless_http=True)

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.fess_client.close()


def main() -> None:
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description="MCP-Fess Bridge Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--cody", action="store_true", help="Use MCP protocol version 2024-11-05")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on for HTTP transport (overrides config, default: 3000)",
    )

    args = parser.parse_args()

    try:
        config = load_config()
        log_dir = ensure_log_directory()

        global logger
        logger, _ = setup_logging(log_dir, args.debug, config.logging.level)

        logger.info("Starting MCP-Fess server")
        logger.info(f"Domain: {config.domain.name} (ID: {config.domain.id})")
        logger.info(f"Fess URL: {config.fessBaseUrl}")
        logger.info(f"Transport: {args.transport}")
        logger.info(f"Protocol version: {'2024-11-05' if args.cody else '2025-03-26'}")

        if (
            args.transport == "http"
            and config.httpTransport.bindAddress not in ["127.0.0.1", "::1", "localhost"]
            and not config.security.allowNonLocalhostBind
        ):
            logger.error("Non-localhost binding requires allowNonLocalhostBind=true")
            sys.exit(1)

        protocol_version = "2024-11-05" if args.cody else "2025-03-26"
        server = FessServer(config, protocol_version)

        async def run_server() -> None:
            try:
                if args.transport == "stdio":
                    await server.run_stdio()
                else:
                    await server.run_http(port_override=args.port)
            finally:
                await server.cleanup()

        asyncio.run(run_server())

    except FileNotFoundError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Server interrupted")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
