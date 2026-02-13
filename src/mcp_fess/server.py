"""MCP Server for Fess."""

import argparse
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

    def _setup_tools(self) -> None:
        """Set up MCP tools using FastMCP decorators."""

        @self.mcp.tool(name=f"fess_{self.domain_id}_search")
        async def search(
            query: str,
            page_size: int = 20,
            start: int = 0,
            sort: str | None = None,
            lang: str | None = None,
            include_fields: list[str] | None = None,
        ) -> str:
            """Search the knowledge domain for documents matching a query."""
            return await self._handle_search(
                {
                    "query": query,
                    "pageSize": page_size,
                    "start": start,
                    "sort": sort,
                    "lang": lang,
                    "includeFields": include_fields,
                }
            )

        @self.mcp.tool(name=f"fess_{self.domain_id}_suggest")
        async def suggest(
            prefix: str,
            num: int = 10,
            fields: list[str] | None = None,
            lang: str | None = None,
        ) -> str:
            """Suggest related terms for a query in the knowledge domain."""
            return await self._handle_suggest(
                {
                    "prefix": prefix,
                    "num": num,
                    "fields": fields,
                    "lang": lang,
                }
            )

        @self.mcp.tool(name=f"fess_{self.domain_id}_popular_words")
        async def popular_words(
            seed: int | None = None,
            field: str | None = None,
        ) -> str:
            """Retrieve popular words in the knowledge domain."""
            return await self._handle_popular_words(
                {
                    "seed": seed,
                    "field": field,
                }
            )

        @self.mcp.tool(name=f"fess_{self.domain_id}_list_labels")
        async def list_labels() -> str:
            """List all labels configured in the underlying Fess server."""
            return await self._handle_list_labels()

        @self.mcp.tool(name=f"fess_{self.domain_id}_health")
        async def health() -> str:
            """Check the health status of the underlying Fess server."""
            return await self._handle_health()

        @self.mcp.tool(name=f"fess_{self.domain_id}_job_get")
        async def job_get(job_id: str) -> str:
            """Retrieve progress information for a long-running operation."""
            return await self._handle_job_get({"jobId": job_id})

    def _setup_resources(self) -> None:
        """Set up MCP resources using FastMCP decorators."""

        @self.mcp.resource(f"fess://{self.domain_id}/doc/{{doc_id}}")
        async def read_doc(doc_id: str) -> str:
            """Document metadata."""
            try:
                result = await self.fess_client.search(
                    query=f"doc_id:{doc_id}",
                    label_filter=self.config.domain.labelFilter,
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

        @self.mcp.resource(f"fess://{self.domain_id}/doc/{{doc_id}}/content")
        async def read_doc_content(doc_id: str) -> str:
            """Full document content."""
            try:
                result = await self.fess_client.search(
                    query=f"doc_id:{doc_id}",
                    label_filter=self.config.domain.labelFilter,
                    num=1,
                )

                docs = result.get("data", [])
                if not docs:
                    raise ValueError(f"Document not found: {doc_id}")

                doc = docs[0]
                url = doc.get("url", "")
                if not url:
                    raise ValueError("Document has no URL")

                content, _ = await self.fess_client.fetch_document_content(
                    url, self.config.contentFetch
                )

                max_chunk = self.config.limits.maxChunkBytes
                if len(content) <= max_chunk:
                    return content
                else:
                    return content[:max_chunk]

            except Exception as e:
                logger.error(f"Failed to read resource: {e}")
                raise

    async def _handle_search(self, arguments: dict[str, Any]) -> str:
        """Handle search tool."""
        query = arguments.get("query")
        if not query:
            raise ValueError("query parameter is required")

        page_size = arguments.get("pageSize", 20)
        if not isinstance(page_size, int) or page_size < 1:
            raise ValueError("pageSize must be a positive integer")
        page_size = min(page_size, self.config.limits.maxPageSize)

        start = arguments.get("start", 0)
        if not isinstance(start, int) or start < 0:
            raise ValueError("start must be a non-negative integer")

        sort = arguments.get("sort")
        lang = arguments.get("lang")

        result = await self.fess_client.search(
            query=query,
            label_filter=self.config.domain.labelFilter,
            start=start,
            num=page_size,
            sort=sort,
            lang=lang,
        )

        return json.dumps(result, indent=2)

    async def _handle_suggest(self, arguments: dict[str, Any]) -> str:
        """Handle suggest tool."""
        prefix = arguments.get("prefix")
        if not prefix:
            raise ValueError("prefix parameter is required")

        num = arguments.get("num", 10)
        if not isinstance(num, int) or num < 1:
            raise ValueError("num must be a positive integer")

        fields = arguments.get("fields")
        lang = arguments.get("lang")

        result = await self.fess_client.suggest(
            prefix=prefix,
            label=self.config.domain.labelFilter,
            num=num,
            fields=fields,
            lang=lang,
        )

        return json.dumps(result, indent=2)

    async def _handle_popular_words(self, arguments: dict[str, Any]) -> str:
        """Handle popular words tool."""
        seed = arguments.get("seed")
        field = arguments.get("field")

        result = await self.fess_client.popular_words(
            label=self.config.domain.labelFilter, seed=seed, field=field
        )

        return json.dumps(result, indent=2)

    async def _handle_list_labels(self) -> str:
        """Handle list labels tool."""
        result = await self.fess_client.list_labels()

        return json.dumps(result, indent=2)

    async def _handle_health(self) -> str:
        """Handle health check tool."""
        result = await self.fess_client.health()

        return json.dumps(result, indent=2)

    async def _handle_job_get(self, arguments: dict[str, Any]) -> str:
        """Handle job status query."""
        job_id = arguments.get("jobId")
        if not job_id:
            raise ValueError("jobId parameter is required")

        if job_id not in self.jobs:
            return f'{{"error": "Job not found", "jobId": "{job_id}"}}'

        job = self.jobs[job_id]

        return json.dumps(job, indent=2)

    async def run_stdio(self) -> None:
        """Run server with stdio transport."""
        await self.mcp.run_stdio_async()

    async def run_http(self) -> None:
        """Run server with HTTP transport."""
        bind_addr = self.config.httpTransport.bindAddress
        port = self.config.httpTransport.port
        if port == 0:
            port = 3000

        logger.info(f"Starting HTTP server on {bind_addr}:{port}{self.config.httpTransport.path}")

        await self.mcp.run_http_async(host=bind_addr, port=port)

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
                    await server.run_http()
            finally:
                await server.cleanup()

        import asyncio

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
