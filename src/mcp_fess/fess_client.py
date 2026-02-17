"""Fess API client."""

import asyncio
import hashlib
import logging
import time
from io import BytesIO
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import ContentFetchConfig

logger = logging.getLogger("mcp_fess")


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
        logger.debug(f"Searching Fess: {url} with params: {params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
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
        logger.debug(f"Getting suggestions: {url} with params: {params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
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
        logger.debug(f"Getting popular words: {url} with params: {params}")

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess popular words error: {e}")
            raise

    async def list_labels(self) -> dict[str, Any]:
        """List all labels in Fess."""
        url = urljoin(self.base_url, "/api/v1/labels")
        logger.debug(f"Listing labels: {url}")

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess list labels error: {e}")
            raise

    async def health(self) -> dict[str, Any]:
        """Check Fess health status."""
        url = urljoin(self.base_url, "/api/v1/health")
        logger.debug(f"Checking health: {url}")

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPError as e:
            logger.error(f"Fess health check error: {e}")
            raise

    async def fetch_document_content_by_id(self, doc_id: str) -> tuple[str, str]:
        """
        Fetch document content from Fess by document ID.

        This method is used as a fallback for file:// URLs, fetching content
        directly from Fess storage via the /api/v1/documents/{docId} endpoint.

        Args:
            doc_id: The Fess document ID

        Returns:
            Tuple of (content, hash)

        Raises:
            ValueError: If document cannot be fetched
            httpx.HTTPError: If HTTP request fails
        """
        # Try to fetch document content via Fess API
        # Fess stores the full content and we can retrieve it via the search API
        url = urljoin(self.base_url, f"/api/v1/documents")
        logger.debug(f"Fetching document content by ID from Fess: {doc_id}")

        try:
            # Search for the specific document by ID
            result = await self.search(query=f"doc_id:{doc_id}", num=1)
            docs = result.get("data", [])

            if not docs:
                raise ValueError(f"Document not found in Fess: {doc_id}")

            doc = docs[0]

            # Get the content from the document metadata
            # Fess typically stores the full content in the 'content' or 'body' field
            content = doc.get("content", "") or doc.get("body", "")

            if not content:
                # Try to get content from 'digest' field as a fallback
                content = doc.get("digest", "")

            if not content:
                raise ValueError(
                    f"Document {doc_id} found but has no retrievable content. "
                    "The document may not have indexed content available."
                )

            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return content, content_hash

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch document content by ID {doc_id}: {e}")
            raise ValueError(
                f"Unable to fetch document content for {doc_id} from Fess API: {e}"
            ) from e

    async def fetch_document_content(self, url: str, config: ContentFetchConfig, doc_id: str | None = None) -> tuple[str, str]:
        """
        Fetch full document content from URL.

        For file:// URLs, attempts to fetch content via Fess API using the document ID.
        For http/https URLs, fetches content directly from the URL.

        Args:
            url: The document URL
            config: Content fetch configuration
            doc_id: Optional document ID for file:// URL fallback

        Returns:
            Tuple of (content, hash)

        Raises:
            ValueError: If content fetching fails or is disabled
            httpx.HTTPError: If HTTP request fails
        """
        if not config.enabled:
            raise ValueError("Content fetching is disabled")

        parsed = urlparse(url)

        # Handle file:// scheme by fetching via Fess API
        if parsed.scheme == "file":
            if not doc_id:
                raise ValueError(
                    "Cannot fetch file:// URL without document ID. "
                    "Please obtain the document ID from search results and use fetch_content_chunk tool."
                )

            logger.info(f"Detected file:// URL, fetching content via Fess API for doc_id: {doc_id}")
            try:
                return await self.fetch_document_content_by_id(doc_id)
            except Exception as e:
                logger.error(f"Failed to fetch file:// URL via Fess API: {e}")
                raise ValueError(
                    f"Unable to fetch content for file:// URL. "
                    f"Fess API fallback failed: {e}"
                ) from e

        # Check allowed schemes for non-file URLs
        if parsed.scheme not in config.allowedSchemes:
            raise ValueError(
                f"Scheme '{parsed.scheme}' is not allowed. "
                f"Allowed schemes: {', '.join(config.allowedSchemes)}. "
                f"For file:// URLs, ensure document ID is provided for Fess API fallback."
            )

        if (
            not config.allowPrivateNetworkTargets
            and self._is_private_network(parsed.hostname or "")
            and (
                not config.allowedHostAllowlist
                or parsed.hostname not in config.allowedHostAllowlist
            )
        ):
            raise ValueError(f"Access to private network target {parsed.hostname} not allowed")

        headers = {"User-Agent": config.userAgent}
        timeout = config.timeoutMs / 1000.0

        logger.debug(f"Fetching content from: {url}")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                content_bytes = response.content[: config.maxBytes]

                if "html" in content_type:
                    content = self._extract_text_from_html(content_bytes)
                elif "pdf" in content_type:
                    if not config.enablePdf:
                        raise ValueError("PDF conversion is disabled")
                    content = self._extract_text_from_pdf(content_bytes)
                else:
                    content = content_bytes.decode("utf-8", errors="ignore")

                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                return content, content_hash

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch content from {url}: {e}")
            raise

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
