"""MCP Server for Fess."""

import argparse
import asyncio
import json
import logging
import re
import sys
from typing import Any

from fastmcp import FastMCP

from .config import ServerConfig, ensure_log_directory, load_config
from .fess_client import FessClient
from .logging_utils import setup_logging

logger = logging.getLogger("mcp_fess")


def _extract_query_terms(query: str) -> list[str]:
    """Extract searchable terms from a query string, stripping operators and punctuation."""
    cleaned = re.sub(r"\b(AND|OR|NOT)\b", " ", query, flags=re.IGNORECASE)
    cleaned = cleaned.replace('"', "").replace("'", "")
    terms = []
    for token in cleaned.split():
        token = token.strip(".,;:!?()[]{}|\\")
        if token and len(token) > 1:
            terms.append(token)
    return terms


def _apply_highlight(fragment: str, terms: list[str], tag_pre: str, tag_post: str) -> str:
    """Apply highlight tags to matched terms in fragment, longest terms first, no overlaps."""
    if not terms:
        return fragment

    fragment_lower = fragment.lower()
    spans: list[tuple[int, int]] = []

    for term in sorted(terms, key=len, reverse=True):
        term_lower = term.lower()
        pos = 0
        while pos < len(fragment):
            idx = fragment_lower.find(term_lower, pos)
            if idx == -1:
                break
            end = idx + len(term)
            # Skip if overlaps with an already-placed span
            if all(e <= idx or s >= end for s, e in spans):
                spans.append((idx, end))
            pos = idx + 1

    if not spans:
        return fragment

    spans.sort()
    result = []
    pos = 0
    for start, end in spans:
        result.append(fragment[pos:start])
        result.append(tag_pre + fragment[start:end] + tag_post)
        pos = end
    result.append(fragment[pos:])
    return "".join(result)


def _generate_snippets(
    text: str,
    query_terms: list[str],
    size_chars: int,
    max_fragments: int,
    tag_pre: str,
    tag_post: str,
    scan_max_chars: int,
) -> list[str]:
    """Generate highlighted text snippets client-side from index text.

    Scans the first scan_max_chars of text for query term occurrences,
    builds windows of size_chars around each match, applies highlight markup,
    and deduplicates overlapping windows.
    """
    if not text:
        return []

    if not query_terms:
        fragment = text[:size_chars]
        suffix = "\u2026" if len(text) > size_chars else ""
        return [fragment + suffix]

    text_lower = text.lower()
    scan_limit = min(len(text), scan_max_chars)

    # Collect match positions within the scan window (stop early if enough found)
    match_positions: list[int] = []
    seen: set[int] = set()

    for term in query_terms:
        term_lower = term.lower()
        pos = 0
        while pos < scan_limit and len(match_positions) < max_fragments * 5:
            idx = text_lower.find(term_lower, pos, scan_limit)
            if idx == -1:
                break
            if idx not in seen:
                match_positions.append(idx)
                seen.add(idx)
            pos = idx + 1

    if not match_positions:
        # No matches - return start of text as fallback
        fragment = text[:size_chars]
        suffix = "\u2026" if len(text) > size_chars else ""
        return [fragment + suffix]

    match_positions.sort()

    # Build non-overlapping windows around matches
    windows: list[tuple[int, int]] = []
    last_win_end = -1

    for match_pos in match_positions:
        half = size_chars // 2
        win_start = max(0, match_pos - half)
        win_end = min(len(text), win_start + size_chars)
        # Adjust window if we bumped into the end
        if win_end - win_start < size_chars:
            win_start = max(0, win_end - size_chars)

        # Skip windows that overlap with the previous one
        if win_start < last_win_end:
            continue

        windows.append((win_start, win_end))
        last_win_end = win_end

        if len(windows) >= max_fragments:
            break

    # Build highlighted fragments
    fragments = []
    for win_start, win_end in windows:
        fragment = text[win_start:win_end]
        prefix = "\u2026" if win_start > 0 else ""
        suffix = "\u2026" if win_end < len(text) else ""
        highlighted = _apply_highlight(fragment, query_terms, tag_pre, tag_post)
        fragments.append(prefix + highlighted + suffix)

    return fragments


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
            snippets: bool = False,
            snippet_size_chars: int | None = None,
            snippet_fragments: int | None = None,
            snippet_docs: int | None = None,
            snippet_tag_pre: str = "<em>",
            snippet_tag_post: str = "</em>",
            snippet_scan_max_chars: int | None = None,
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
                    "snippets": snippets,
                    "snippet_size_chars": snippet_size_chars,
                    "snippet_fragments": snippet_fragments,
                    "snippet_docs": snippet_docs,
                    "snippet_tag_pre": snippet_tag_pre,
                    "snippet_tag_post": snippet_tag_post,
                    "snippet_scan_max_chars": snippet_scan_max_chars,
                }
            )

        # Set dynamic descriptor for search tool
        search.__doc__ = f"""Search the Fess index and return ranked document hits.
Use this first to turn a keyword/question into a shortlist of candidate documents (capture `doc_id`).

{self._descriptor_workflow()}

**Note:** Search hits may include only short summary/snippet fields. For substantial text evidence, always use the content fetch tool/resource.

**Performance:** Use `include_fields` to limit payload to the fields you need.

**Snippets (optional):** Set `snippets=true` to attach client-side generated text snippets to each hit.
Snippets are generated by mcp-fess from index text (priority: `content` → `body` → `digest`);
they are NOT Fess highlight fragments. Snippet size and count are clamped to configured limits.
For long-form evidence, prefer `fetch_content_chunk` instead.

Args:
    query: Search term
    label: Label value to scope the search (default uses configured defaultLabel).
           Use 'all' to search across the entire index without label filtering.
           Call list_labels to see available labels.
    page_size: Number of results per page (default 20, max {self.config.limits.maxPageSize})
    start: Starting index for pagination (default 0)
    sort: Sort order
    lang: Search language
    include_fields: Fields to include in results
    snippets: Set to true to attach generated snippets to each hit (default false)
    snippet_size_chars: Desired chars per snippet fragment (clamped to [{self.config.limits.snippetMinChars}, {self.config.limits.snippetMaxChars}], default {self.config.limits.snippetDefaultChars})
    snippet_fragments: Max fragments per hit (clamped to [1, {self.config.limits.snippetMaxFragments}], default {self.config.limits.snippetDefaultFragments})
    snippet_docs: Max hits to enrich with snippets (clamped to [1, {self.config.limits.snippetMaxDocs}], default {self.config.limits.snippetDefaultDocs})
    snippet_tag_pre: Opening highlight tag (default '<em>')
    snippet_tag_post: Closing highlight tag (default '</em>')
    snippet_scan_max_chars: Max chars of document text to scan for matches (default {self.config.limits.snippetScanMaxChars})"""

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

    def _validate_and_clamp_snippet_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate and clamp snippet generation arguments against configured limits.

        Returns a dict with effective (clamped) values ready for use.
        """
        limits = self.config.limits
        clamped = False

        # snippet_size_chars
        raw_size = arguments.get("snippet_size_chars")
        if raw_size is None:
            effective_size = limits.snippetDefaultChars
        else:
            if not isinstance(raw_size, int) or raw_size < 1:
                raise ValueError("snippet_size_chars must be a positive integer")
            if raw_size < limits.snippetMinChars:
                effective_size = limits.snippetMinChars
                clamped = True
            elif raw_size > limits.snippetMaxChars:
                effective_size = limits.snippetMaxChars
                clamped = True
            else:
                effective_size = raw_size

        # snippet_fragments
        raw_fragments = arguments.get("snippet_fragments")
        if raw_fragments is None:
            effective_fragments = limits.snippetDefaultFragments
        else:
            if not isinstance(raw_fragments, int) or raw_fragments < 1:
                raise ValueError("snippet_fragments must be a positive integer")
            if raw_fragments > limits.snippetMaxFragments:
                effective_fragments = limits.snippetMaxFragments
                clamped = True
            else:
                effective_fragments = raw_fragments

        # snippet_docs
        raw_docs = arguments.get("snippet_docs")
        if raw_docs is None:
            effective_docs = limits.snippetDefaultDocs
        else:
            if not isinstance(raw_docs, int) or raw_docs < 1:
                raise ValueError("snippet_docs must be a positive integer")
            if raw_docs > limits.snippetMaxDocs:
                effective_docs = limits.snippetMaxDocs
                clamped = True
            else:
                effective_docs = raw_docs

        # snippet_scan_max_chars
        raw_scan = arguments.get("snippet_scan_max_chars")
        if raw_scan is None:
            effective_scan = limits.snippetScanMaxChars
        else:
            if not isinstance(raw_scan, int) or raw_scan < 1:
                raise ValueError("snippet_scan_max_chars must be a positive integer")
            if raw_scan > limits.snippetScanMaxChars:
                effective_scan = limits.snippetScanMaxChars
                clamped = True
            else:
                effective_scan = raw_scan

        tag_pre = arguments.get("snippet_tag_pre", "<em>")
        tag_post = arguments.get("snippet_tag_post", "</em>")

        return {
            "snippet_size_chars": effective_size,
            "snippet_fragments": effective_fragments,
            "snippet_docs": effective_docs,
            "snippet_scan_max_chars": effective_scan,
            "snippet_tag_pre": tag_pre,
            "snippet_tag_post": tag_post,
            "clamped": clamped,
        }

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

        # Optionally enrich hits with client-side generated snippets
        if arguments.get("snippets"):
            snippet_params = self._validate_and_clamp_snippet_args(arguments)
            hits = result.get("data", [])
            enrichable_hits = hits[: snippet_params["snippet_docs"]]
            query_terms = _extract_query_terms(query)

            semaphore = asyncio.Semaphore(self.config.limits.maxInFlightRequests)

            async def _enrich_hit(hit: dict[str, Any]) -> None:
                async with semaphore:
                    doc_id = hit.get("doc_id")
                    if not doc_id:
                        return
                    try:
                        text = await self.fess_client.get_extracted_text_by_doc_id(
                            doc_id, label_filter=label_filter
                        )
                        snippets_list = _generate_snippets(
                            text=text,
                            query_terms=query_terms,
                            size_chars=snippet_params["snippet_size_chars"],
                            max_fragments=snippet_params["snippet_fragments"],
                            tag_pre=snippet_params["snippet_tag_pre"],
                            tag_post=snippet_params["snippet_tag_post"],
                            scan_max_chars=snippet_params["snippet_scan_max_chars"],
                        )
                        hit["mcp_snippets"] = {
                            "requested_size_chars": arguments.get("snippet_size_chars"),
                            "effective_size_chars": snippet_params["snippet_size_chars"],
                            "requested_fragments": arguments.get("snippet_fragments"),
                            "effective_fragments": snippet_params["snippet_fragments"],
                            "source_field": "content/body/digest",
                            "snippets": snippets_list,
                            "clamped": snippet_params["clamped"],
                        }
                    except Exception as e:
                        logger.warning(f"Failed to generate snippets for doc_id={doc_id}: {e}")
                        hit["mcp_snippets"] = {"error": str(e)}

            await asyncio.gather(*[_enrich_hit(hit) for hit in enrichable_hits])

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
            raise ValueError(
                f"Requested chunk size {length} exceeds server limit {max_chunk_bytes}."
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
                "metadata": {
                    "max_chunk_size": max_chunk_bytes,
                },
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
                "metadata": {
                    "max_chunk_size": max_bytes,
                },
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
