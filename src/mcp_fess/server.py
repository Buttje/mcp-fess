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
            """Search documents in Fess.

            Use this tool whenever you need factual internal information; don't guess—search first.
            If unsure which label to use, call the list_labels tool first.

            Args:
                query: Search term
                label: Label value to scope the search (default uses configured defaultLabel).
                       Use 'all' to search across the entire index without label filtering.
                       Call list_labels to see available labels.
                page_size: Number of results (default 20, max 100)
                start: Starting index (default 0)
                sort: Sort order
                lang: Search language
                include_fields: Fields to include in results
            """
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
            """List available Fess labels and what each label contains.

            Call this tool if unsure which label to use for searching.
            Returns label values with descriptions, examples, and availability status.
            """
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

        @self.mcp.resource(f"fess://{self.domain_id}/doc/{{doc_id}}/content")
        async def read_doc_content(doc_id: str) -> str:
            """Full document content."""
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

        @self.mcp.resource(f"fess://{self.domain_id}/labels")
        async def read_labels() -> str:
            """Available Fess labels with descriptions."""
            return await self._handle_list_labels()

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

        # Use default label if it's not "all"
        label = None if self.default_label == "all" else self.default_label

        result = await self.fess_client.suggest(
            prefix=prefix,
            label=label,
            num=num,
            fields=fields,
            lang=lang,
        )

        return json.dumps(result, indent=2)

    async def _handle_popular_words(self, arguments: dict[str, Any]) -> str:
        """Handle popular words tool."""
        seed = arguments.get("seed")
        field = arguments.get("field")

        # Use default label if it's not "all"
        label = None if self.default_label == "all" else self.default_label

        result = await self.fess_client.popular_words(label=label, seed=seed, field=field)

        return json.dumps(result, indent=2)

    async def _handle_list_labels(self) -> str:
        """Handle list labels tool.

        Returns merged catalog of labels from config and Fess with descriptions.
        """
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
