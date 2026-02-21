"""Fess API client."""

import asyncio
import hashlib
import logging
import time
from io import BytesIO
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import ContentFetchConfig

logger = logging.getLogger("mcp_fess")


def truncate_text_utf8_safe(text: str, max_bytes: int) -> tuple[str, bool]:
    """
    Truncate text to max_bytes safely without splitting UTF-8 multibyte sequences.

    Args:
        text: Text to truncate
        max_bytes: Maximum number of UTF-8 bytes

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    if not text:
        return text, False

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False

    # Truncate at byte boundary and decode with error handling
    # This will drop any partial multibyte sequence at the end
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True



class LabelCache:
    """Cache for Fess labels with TTL."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        """Initialize label cache with TTL (default 5 minutes)."""
        self.ttl_seconds = ttl_seconds
        self._labels: list[dict[str, Any]] = []
        self._last_fetch: float = 0
        self._lock = asyncio.Lock()

    def is_expired(self) -> bool:
        """Check if cache is expired."""
        return time.time() - self._last_fetch > self.ttl_seconds

    async def get(self) -> list[dict[str, Any]]:
        """Get cached labels."""
        async with self._lock:
            return self._labels.copy()

    async def set(self, labels: list[dict[str, Any]]) -> None:
        """Set cached labels."""
        async with self._lock:
            self._labels = labels
            self._last_fetch = time.time()


class FessClient:
    """Client for interacting with Fess REST API."""

    def __init__(self, base_url: str, timeout_ms: int = 30000) -> None:
        self.base_url = base_url
        self.timeout = timeout_ms / 1000.0
        self.client = httpx.AsyncClient(timeout=self.timeout)
        self.label_cache = LabelCache()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_cached_labels(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """
        Get labels with caching.

        Returns list of label dicts with 'name' and 'value' keys.
        Caches results for 5 minutes to avoid hitting Fess on every request.
        """
        if not force_refresh and not self.label_cache.is_expired():
            cached = await self.label_cache.get()
            if cached:
                logger.debug("Returning cached labels")
                return cached

        try:
            logger.debug("Fetching fresh labels from Fess")
            result = await self.list_labels()
            labels: list[dict[str, Any]] = result.get("data", [])
            await self.label_cache.set(labels)
            return labels
        except Exception as e:
            logger.warning(f"Failed to fetch labels from Fess: {e}")
            # Return cached data even if expired when Fess is down
            cached = await self.label_cache.get()
            if cached:
                logger.info("Returning stale cached labels due to Fess error")
                return cached
            return []

    async def search(
        self,
        query: str,
        label_filter: str | None = None,
        start: int = 0,
        num: int = 20,
        sort: str | None = None,
        lang: str | None = None,
        fields: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search documents in Fess."""
        params: dict[str, Any] = {"q": query, "start": start, "num": num}

        if label_filter:
            params["fields.label"] = label_filter
        if sort:
            params["sort"] = sort
        if lang:
            params["lang"] = lang

        for key, value in kwargs.items():
            if value is not None:
                params[key] = value

        url = urljoin(self.base_url, "/api/v1/documents")
        logger.debug(f"Fess REST API call: GET {url} params={params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            logger.debug(
                f"Fess REST API response: GET {url} status={response.status_code} "
                f"hits={result.get('record_count', result.get('hit_count', len(result.get('data', []))))}"
            )
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess search error: {e}")
            raise

    async def suggest(
        self,
        prefix: str,
        label: str | None = None,
        num: int = 10,
        fields: list[str] | None = None,
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Get suggestions from Fess."""
        params: dict[str, Any] = {"q": prefix, "num": num}

        if label:
            params["label"] = label
        if fields:
            params["fields"] = ",".join(fields)
        if lang:
            params["lang"] = lang

        url = urljoin(self.base_url, "/api/v1/suggest-words")
        logger.debug(f"Fess REST API call: GET {url} params={params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            logger.debug(
                f"Fess REST API response: GET {url} status={response.status_code} "
                f"suggestions={len(result.get('data', []))}"
            )
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess suggest error: {e}")
            raise

    async def popular_words(
        self, label: str | None = None, seed: int | None = None, field: str | None = None
    ) -> dict[str, Any]:
        """Get popular words from Fess."""
        params: dict[str, Any] = {}

        if label:
            params["label"] = label
        if seed is not None:
            params["seed"] = seed
        if field:
            params["field"] = field

        url = urljoin(self.base_url, "/api/v1/popular-words")
        logger.debug(f"Fess REST API call: GET {url} params={params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            logger.debug(
                f"Fess REST API response: GET {url} status={response.status_code} "
                f"words={len(result.get('data', []))}"
            )
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess popular words error: {e}")
            raise

    async def list_labels(self) -> dict[str, Any]:
        """List all labels in Fess."""
        url = urljoin(self.base_url, "/api/v1/labels")
        logger.debug(f"Fess REST API call: GET {url}")

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            logger.debug(
                f"Fess REST API response: GET {url} status={response.status_code} "
                f"labels={len(result.get('data', []))}"
            )
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess list labels error: {e}")
            raise

    async def health(self) -> dict[str, Any]:
        """Check Fess health status."""
        url = urljoin(self.base_url, "/api/v1/health")
        logger.debug(f"Fess REST API call: GET {url}")

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            logger.debug(
                f"Fess REST API response: GET {url} status={response.status_code} "
                f"health={result.get('status', 'unknown')}"
            )
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess health check error: {e}")
            raise

    async def get_extracted_text_by_doc_id(
        self, doc_id: str, label_filter: str | None = None
    ) -> str:
        """
        Get extracted text from Fess index by document ID.

        This method retrieves text content exclusively from the Fess search index,
        using the text field priority: content → body → digest.

        Args:
            doc_id: The Fess document ID
            label_filter: Optional label filter to apply (None for "all")

        Returns:
            Extracted text content as a string

        Raises:
            ValueError: If document is not found or has no extracted text available
        """
        logger.debug(
            f"Fetching extracted text from Fess index for doc_id={doc_id}, "
            f"label_filter={label_filter}"
        )

        try:
            # Search for the specific document by ID
            result = await self.search(
                query=f"doc_id:{doc_id}", label_filter=label_filter, num=1, start=0
            )
            docs = result.get("data", [])

            if not docs:
                raise ValueError(f"Document not found for doc_id={doc_id}")

            doc = docs[0]

            # Text field priority: content → body → digest
            # Normalize to handle list types (some Fess configs return lists)
            def normalize_field(value: Any) -> str:
                """Normalize field value to string."""
                if value is None:
                    return ""
                if isinstance(value, list):
                    # Join list items if it's a list
                    return "\n\n".join(str(item) for item in value if item)
                return str(value).strip()

            content = normalize_field(doc.get("content"))
            if content:
                logger.info(
                    f"Retrieved content from 'content' field for doc_id={doc_id}, "
                    f"length={len(content)}"
                )
                return content

            body = normalize_field(doc.get("body"))
            if body:
                logger.info(
                    f"Retrieved content from 'body' field for doc_id={doc_id}, "
                    f"length={len(body)}"
                )
                return body

            digest = normalize_field(doc.get("digest"))
            if digest:
                logger.info(
                    f"Retrieved content from 'digest' field for doc_id={doc_id}, "
                    f"length={len(digest)}"
                )
                return digest

            # No text available
            raise ValueError(
                f"No extracted text available in Fess index for doc_id={doc_id}. "
                "Ensure Fess is configured to store extracted content "
                "(e.g., content/body) in the index."
            )

        except ValueError:
            # Re-raise ValueError as-is
            raise
        except Exception as e:
            logger.error(f"Failed to fetch extracted text for doc_id={doc_id}: {e}")
            raise ValueError(
                f"Unable to fetch extracted text for {doc_id} from Fess index: {e}"
            ) from e

    async def fetch_document_content_by_id(self, doc_id: str) -> tuple[str, str]:
        """
        Fetch document content from Fess by document ID.

        This is a compatibility wrapper around get_extracted_text_by_doc_id.
        All content is retrieved from the Fess index only.

        Args:
            doc_id: The Fess document ID

        Returns:
            Tuple of (content, hash)

        Raises:
            ValueError: If document cannot be fetched
        """
        logger.debug(f"Fetching document content by ID from Fess index: {doc_id}")

        # Use the new index-only method
        content = await self.get_extracted_text_by_doc_id(doc_id, label_filter=None)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return content, content_hash

    async def fetch_document_content(
        self, url: str, config: ContentFetchConfig, doc_id: str | None = None
    ) -> tuple[str, str]:
        """
        Fetch document content from Fess index only.

        This method now retrieves all content exclusively from the Fess search index,
        regardless of the URL scheme. It does not fetch content directly from URLs.

        Args:
            url: The document URL (used for logging only, not fetched)
            config: Content fetch configuration (for compatibility)
            doc_id: Document ID (required for content retrieval)

        Returns:
            Tuple of (content, hash)

        Raises:
            ValueError: If content fetching fails or doc_id is missing
        """
        if not config.enabled:
            raise ValueError("Content fetching is disabled")

        if not doc_id:
            raise ValueError(
                "Document ID is required for content retrieval. "
                "Content is now retrieved exclusively from the Fess index."
            )

        scheme = url.split("://")[0].lower() if url and "://" in url else ""
        logger.debug(
            f"fetch_document_content called: url={url} doc_id={doc_id} url_scheme={scheme!r} "
            f"(index-only retrieval; URL is not fetched)"
        )

        logger.info(
            f"Fetching content from Fess index for doc_id={doc_id} (url={url}, source=fess_index)"
        )

        # Use the new index-only method
        return await self.fetch_document_content_by_id(doc_id)

    def _is_private_network(self, hostname: str) -> bool:
        """Check if hostname is a private network address."""
        if not hostname:
            return False

        if hostname in ["localhost", "127.0.0.1", "::1"]:
            return True

        parts = hostname.split(".")
        if len(parts) == 4:
            try:
                first = int(parts[0])
                second = int(parts[1])
                if first == 10:
                    return True
                if first == 172 and 16 <= second <= 31:
                    return True
                if first == 192 and second == 168:
                    return True
            except ValueError:
                pass

        return False

    def _extract_text_from_html(self, content: bytes) -> str:
        """Extract text from HTML content."""
        try:
            soup = BeautifulSoup(content, "html.parser")

            for script in soup(["script", "style", "meta", "link"]):
                script.decompose()

            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to parse HTML: {e}")
            return content.decode("utf-8", errors="ignore")

    def _extract_text_from_pdf(self, content: bytes) -> str:
        """Extract text from PDF content."""
        try:
            pdf_file = BytesIO(content)
            reader = PdfReader(pdf_file)

            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            return "\n\n".join(text_parts)
        except Exception as e:
            logger.warning(f"Failed to parse PDF: {e}")
            raise ValueError(f"PDF parsing failed: {e}") from e
