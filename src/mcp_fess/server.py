"""MCP Server for Fess."""

import argparse
import asyncio
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)

from .config import ServerConfig, ensure_log_directory, load_config
from .fess_client import FessClient
from .logging_utils import setup_logging

logger = logging.getLogger("mcp_fess")


class FessServer:
    """MCP server implementation for Fess."""

    def __init__(self, config: ServerConfig, protocol_version: str = "2025-03-26") -> None:
        self.config = config
        self.protocol_version = protocol_version
        self.fess_client = FessClient(
            config.fessBaseUrl, config.timeouts.fessRequestTimeoutMs
        )
        self.server = Server("mcp-fess")
        self.domain_id = config.domain.id
        self.jobs: dict[str, dict[str, Any]] = {}

        self._setup_handlers()

    def _get_domain_block(self) -> str:
        """Generate the Knowledge Domain block for descriptions."""
        domain = self.config.domain
        desc = f"description: {domain.description}" if domain.description else ""
        return f"""[Knowledge Domain]
id: {domain.id}
name: {domain.name}
{desc}
fessLabel: {domain.labelFilter}"""

    def _setup_handlers(self) -> None:
        """Set up MCP request handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available tools."""
            domain_block = self._get_domain_block()
            tools = []

            tools.append(
                Tool(
                    name=f"fess_{self.domain_id}_search",
                    description=f"Search the knowledge domain for documents matching a query.\n\n{domain_block}",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search term"},
                            "pageSize": {
                                "type": "integer",
                                "description": "Number of results (default 20, max 100)",
                                "default": 20,
                            },
                            "start": {
                                "type": "integer",
                                "description": "Starting index (default 0)",
                                "default": 0,
                            },
                            "sort": {"type": "string", "description": "Sort order"},
                            "lang": {"type": "string", "description": "Search language"},
                            "includeFields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Fields to include in results",
                            },
                        },
                        "required": ["query"],
                    },
                )
            )

            tools.append(
                Tool(
                    name=f"fess_{self.domain_id}_suggest",
                    description=f"Suggest related terms for a query in the knowledge domain.\n\n{domain_block}",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "prefix": {"type": "string", "description": "Search prefix"},
                            "num": {
                                "type": "integer",
                                "description": "Number of suggestions (default 10)",
                                "default": 10,
                            },
                            "fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Fields to search in",
                            },
                            "lang": {"type": "string", "description": "Language"},
                        },
                        "required": ["prefix"],
                    },
                )
            )

            tools.append(
                Tool(
                    name=f"fess_{self.domain_id}_popular_words",
                    description=f"Retrieve popular words in the knowledge domain.\n\n{domain_block}",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "seed": {"type": "integer", "description": "Random seed"},
                            "field": {"type": "string", "description": "Field name"},
                        },
                    },
                )
            )

            tools.append(
                Tool(
                    name=f"fess_{self.domain_id}_list_labels",
                    description=f"List all labels configured in the underlying Fess server.\n\n{domain_block}",
                    inputSchema={"type": "object", "properties": {}},
                )
            )

            tools.append(
                Tool(
                    name=f"fess_{self.domain_id}_health",
                    description=f"Check the health status of the underlying Fess server.\n\n{domain_block}",
                    inputSchema={"type": "object", "properties": {}},
                )
            )

            tools.append(
                Tool(
                    name=f"fess_{self.domain_id}_job_get",
                    description=f"Retrieve progress information for a long-running operation.\n\n{domain_block}",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "jobId": {"type": "string", "description": "Job ID"},
                        },
                        "required": ["jobId"],
                    },
                )
            )

            return tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            logger.info(f"Tool called: {name} with arguments: {arguments}")

            try:
                if name == f"fess_{self.domain_id}_search":
                    return await self._handle_search(arguments)
                elif name == f"fess_{self.domain_id}_suggest":
                    return await self._handle_suggest(arguments)
                elif name == f"fess_{self.domain_id}_popular_words":
                    return await self._handle_popular_words(arguments)
                elif name == f"fess_{self.domain_id}_list_labels":
                    return await self._handle_list_labels()
                elif name == f"fess_{self.domain_id}_health":
                    return await self._handle_health()
                elif name == f"fess_{self.domain_id}_job_get":
                    return await self._handle_job_get(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as e:
                logger.error(f"Tool execution error: {e}", exc_info=True)
                return [TextContent(type="text", text=f"Error: {e!s}")]

        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available resources."""
            domain_block = self._get_domain_block()
            try:
                result = await self.fess_client.search(
                    query="*",
                    label_filter=self.config.domain.labelFilter,
                    start=0,
                    num=self.config.limits.maxPageSize,
                )

                resources = []
                for doc in result.get("data", []):
                    doc_id = doc.get("doc_id", "")
                    title = doc.get("title", "Untitled")
                    url = doc.get("url", "")

                    resources.append(
                        Resource(
                            uri=f"fess://{self.domain_id}/doc/{doc_id}",
                            name=title,
                            description=f"{domain_block}\n\nDocument: {title}\nURL: {url}",
                            mimeType="text/plain",
                        )
                    )

                return resources
            except Exception as e:
                logger.error(f"Failed to list resources: {e}")
                return []

        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read resource content."""
            logger.info(f"Reading resource: {uri}")

            if not uri.startswith(f"fess://{self.domain_id}/doc/"):
                raise ValueError(f"Invalid resource URI: {uri}")

            parts = uri.split("/")
            if len(parts) < 5:
                raise ValueError(f"Invalid resource URI format: {uri}")

            doc_id = parts[4]
            is_content = len(parts) > 5 and parts[5] == "content"

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

                if is_content:
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
                else:
                    import json

                    return json.dumps(doc, indent=2)

            except Exception as e:
                logger.error(f"Failed to read resource: {e}")
                raise

    async def _handle_search(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle search tool."""
        query = arguments["query"]
        page_size = min(arguments.get("pageSize", 20), self.config.limits.maxPageSize)
        start = arguments.get("start", 0)
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

        import json

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _handle_suggest(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle suggest tool."""
        prefix = arguments["prefix"]
        num = arguments.get("num", 10)
        fields = arguments.get("fields")
        lang = arguments.get("lang")

        result = await self.fess_client.suggest(
            prefix=prefix,
            label=self.config.domain.labelFilter,
            num=num,
            fields=fields,
            lang=lang,
        )

        import json

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _handle_popular_words(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle popular words tool."""
        seed = arguments.get("seed")
        field = arguments.get("field")

        result = await self.fess_client.popular_words(
            label=self.config.domain.labelFilter, seed=seed, field=field
        )

        import json

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _handle_list_labels(self) -> list[TextContent]:
        """Handle list labels tool."""
        result = await self.fess_client.list_labels()

        import json

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _handle_health(self) -> list[TextContent]:
        """Handle health check tool."""
        result = await self.fess_client.health()

        import json

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _handle_job_get(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle job status query."""
        job_id = arguments["jobId"]

        if job_id not in self.jobs:
            return [TextContent(type="text", text=f"Job not found: {job_id}")]

        job = self.jobs[job_id]

        import json

        return [TextContent(type="text", text=json.dumps(job, indent=2))]

    async def run_stdio(self) -> None:
        """Run server with stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )

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
    parser.add_argument(
        "--cody", action="store_true", help="Use MCP protocol version 2024-11-05"
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

        if args.transport == "stdio":
            asyncio.run(server.run_stdio())
        else:
            logger.error("HTTP transport not yet implemented")
            sys.exit(1)

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

