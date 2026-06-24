"""
Hardened "Add Content from URL" ingestion for the RAG knowledge base.

Pipeline (reuses the same chunker + embeddings + FAISS store as file upload):
    validate URL (SSRF guard) -> async fetch (timeout / size cap / UA / bounded
    redirects) -> branch on content-type (PDF routed through the existing document
    loader; HTML extracted with trafilatura, falling back to BeautifulSoup) ->
    chunk -> attach metadata (source_type/source_url/title/tags/fetched_at/
    content_hash) -> idempotent upsert into the shared vector store.

Auth note: this module performs no authorization. Endpoints that expose it are
classified admin-only via `app.auth.require_admin` (see app/admin.py).
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import logger
from .rag import vectorstore_manager

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
FETCH_TIMEOUT = 15.0            # seconds (connect + read)
MAX_CONTENT_BYTES = 10 * 1024 * 1024  # 10 MB cap on fetched body
MAX_REDIRECTS = 3
USER_AGENT = "SmartAI-RAG-Ingest/1.0 (+admin url ingestion)"

# Chunking config mirrors the document-upload pipeline (admin.load_documents_from_*).
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CHUNK_SEPARATORS = ["\n\n", "\n", " ", ""]

# Idempotency registry: source_url -> {content_hash, ids, chunks, title, tags, fetched_at}.
REGISTRY_PATH = Path("data/url_ingest_registry.json")

# Content types we treat as HTML/text vs. PDF. Anything else is rejected.
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_TEXT_TYPES = ("text/plain", "text/markdown")
_PDF_TYPES = ("application/pdf",)

# TLS verification (env-configurable for corporate proxies / SSL inspection):
#   URL_INGEST_CA_BUNDLE   -> path to a custom CA bundle (.pem) to trust.
#   URL_INGEST_VERIFY_SSL  -> "false"/"0"/"no" disables verification (DEV ONLY).
# Default: trust the OS (Windows/macOS/Linux) certificate store via `truststore`
# when available — this picks up corporate root CAs that httpx's bundled certifi
# does not have. Falls back to certifi if truststore isn't installed.
URL_INGEST_CA_BUNDLE = os.getenv("URL_INGEST_CA_BUNDLE")
URL_INGEST_VERIFY_SSL = os.getenv("URL_INGEST_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no"}


def _build_verify():
    """Return the value for httpx's `verify=` argument based on env config.

    Precedence: explicit opt-out -> custom CA bundle -> OS trust store -> certifi.
    """
    if not URL_INGEST_VERIFY_SSL:
        logger.warning(
            "URL_INGEST_VERIFY_SSL is disabled — TLS certificates will NOT be verified. "
            "Use only in trusted dev environments."
        )
        return False
    if URL_INGEST_CA_BUNDLE:
        logger.info("Using custom CA bundle for URL fetch verification: %s", URL_INGEST_CA_BUNDLE)
        return URL_INGEST_CA_BUNDLE
    try:
        import ssl
        import truststore  # type: ignore

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        logger.debug("Using OS trust store (truststore) for URL fetch verification")
        return ctx
    except Exception as exc:  # truststore missing or unusable -> certifi default
        logger.warning(
            "truststore unavailable (%s); falling back to certifi. If you are behind a "
            "corporate proxy, set URL_INGEST_CA_BUNDLE to your root CA .pem.",
            exc,
        )
        return True


class UrlIngestError(Exception):
    """Raised for any user-facing URL ingestion failure (mapped to HTTP 4xx/5xx)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------
def _ip_is_blocked(ip_str: str) -> bool:
    """True if the IP is private/loopback/link-local/reserved/multicast/unspecified.

    Link-local (169.254.0.0/16, fe80::/10) covers the cloud metadata endpoint
    169.254.169.254, so no special-case is needed for it.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable -> treat as unsafe
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_host(host: str) -> List[str]:
    """Resolve a hostname to all of its A/AAAA addresses. Raises on failure."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UrlIngestError(f"Could not resolve host '{host}': {exc}", status_code=400)
    return list({info[4][0] for info in infos})


def validate_public_url(url: str) -> str:
    """Validate a URL for safe outbound fetching (anti-SSRF).

    Enforces: http/https only, host present, port in {80,443}, and every resolved
    IP address is publicly routable (rejects private/loopback/link-local/metadata).
    Returns the normalized URL. Raises UrlIngestError on any violation.
    """
    parsed = urlparse(url.strip())

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UrlIngestError("Invalid URL. Only http:// and https:// are allowed.")
    if not parsed.hostname:
        raise UrlIngestError("Invalid URL. No host found.")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UrlIngestError(f"Port {port} is not allowed. Only 80 and 443 are permitted.")

    # If the host is a literal IP, check it directly; otherwise resolve and check all.
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = _resolve_host(host)

    if not addresses:
        raise UrlIngestError(f"Could not resolve host '{host}'.")
    for addr in addresses:
        if _ip_is_blocked(addr):
            raise UrlIngestError(
                f"Refusing to fetch '{host}': resolves to a non-public address ({addr}).",
                status_code=400,
            )

    return urlunparse(parsed)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
async def fetch_url(url: str) -> Tuple[bytes, str, str]:
    """Fetch a URL safely and return (body_bytes, content_type, final_url).

    Follows redirects manually (bounded), re-validating each hop against the SSRF
    guard so an open redirect cannot pivot to an internal address. Enforces a read
    timeout and a hard body-size cap (streamed, so oversized bodies abort early).
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    current = validate_public_url(url)

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT, follow_redirects=False, headers=headers, verify=_build_verify()
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise UrlIngestError("Redirect response without a Location header.")
                        current = validate_public_url(str(resp.next_request.url) if resp.next_request else location)
                        continue

                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()

                    # Reject obviously-too-large bodies up front when advertised.
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_CONTENT_BYTES:
                        raise UrlIngestError(
                            f"Content too large ({declared} bytes > {MAX_CONTENT_BYTES} limit).",
                            status_code=413,
                        )

                    chunks: List[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_CONTENT_BYTES:
                            raise UrlIngestError(
                                f"Content exceeds the {MAX_CONTENT_BYTES} byte limit.",
                                status_code=413,
                            )
                        chunks.append(chunk)
                    return b"".join(chunks), content_type, str(resp.url)
            except httpx.TimeoutException:
                raise UrlIngestError("Timed out fetching the URL.", status_code=504)
            except httpx.HTTPStatusError as exc:
                raise UrlIngestError(
                    f"Upstream returned HTTP {exc.response.status_code} for the URL.",
                    status_code=502,
                )
            except httpx.HTTPError as exc:
                raise UrlIngestError(f"Failed to fetch the URL: {exc}", status_code=502)

    raise UrlIngestError(f"Too many redirects (>{MAX_REDIRECTS}).", status_code=502)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def extract_main_text(body: bytes, content_type: str) -> str:
    """Extract readable main content from an HTML/text body.

    Prefers trafilatura (strips nav/ads/boilerplate). Falls back to BeautifulSoup
    text extraction, then to a plain decode, so ingestion still works if optional
    extractors are unavailable.
    """
    if any(content_type.startswith(t) for t in _TEXT_TYPES):
        return body.decode("utf-8", errors="ignore").strip()

    html = body.decode("utf-8", errors="ignore")

    # 1) trafilatura — best boilerplate removal.
    try:
        import trafilatura  # type: ignore

        extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
        if extracted and extracted.strip():
            return extracted.strip()
    except Exception as exc:  # pragma: no cover - optional dependency / parse edge cases
        logger.warning("trafilatura extraction failed (%s); falling back to BeautifulSoup", exc)

    # 2) BeautifulSoup — strip script/style and collapse whitespace.
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            return "\n".join(lines)
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.warning("BeautifulSoup extraction failed (%s); falling back to raw decode", exc)

    # 3) Last resort.
    return html.strip()


def chunk_text(text: str, base_metadata: Dict[str, Any]) -> List[Document]:
    """Split extracted text into LangChain Documents using the shared chunk config."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHUNK_SEPARATORS,
    )
    pieces = splitter.split_text(text)
    return [
        Document(page_content=piece, metadata={**base_metadata, "chunk_index": i})
        for i, piece in enumerate(pieces)
    ]


# ---------------------------------------------------------------------------
# Idempotency registry
# ---------------------------------------------------------------------------
def _load_registry() -> Dict[str, Any]:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("URL ingest registry unreadable (%s); starting fresh", exc)
    return {}


def _save_registry(registry: Dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def list_ingested_urls() -> List[Dict[str, Any]]:
    """Return the URLs currently indexed in the knowledge base (from the registry)."""
    registry = _load_registry()
    return [
        {
            "url": url,
            "title": meta.get("title"),
            "tags": meta.get("tags", []),
            "chunks": meta.get("chunks", len(meta.get("ids", []))),
            "fetched_at": meta.get("fetched_at"),
            "content_hash": meta.get("content_hash"),
        }
        for url, meta in registry.items()
    ]


def delete_ingested_url(url: str) -> Dict[str, Any]:
    """Remove all chunks previously indexed from `url` and drop its registry entry.

    Raises UrlIngestError(404) if the URL was never ingested.
    """
    registry = _load_registry()
    meta = registry.get(url)
    if not meta:
        raise UrlIngestError(f"No ingested content found for URL: {url}", status_code=404)

    deleted = 0
    ids = meta.get("ids") or []
    if ids:
        deleted = vectorstore_manager.delete_documents(ids)
    registry.pop(url, None)
    _save_registry(registry)
    logger.info("Deleted ingested URL %s (%d chunks removed)", url, deleted)
    return {"url": url, "chunks_deleted": deleted, "status": "deleted"}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
async def ingest_url(
    url: str,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Fetch, extract, chunk, and index a URL into the shared vector store.

    Idempotent: if the URL was indexed before and its content is unchanged, the
    re-index is skipped unless `force=True`. On a forced/changed re-fetch the prior
    chunks for that URL are deleted before the new ones are added.

    Returns an ingestion summary dict.
    """
    tags = tags or []
    safe_url = validate_public_url(url)

    body, content_type, final_url = await fetch_url(safe_url)
    fetched_at = datetime.now(timezone.utc).isoformat()

    # PDF -> route through the EXISTING document pipeline (save then load+chunk).
    if any(content_type.startswith(t) for t in _PDF_TYPES):
        return await _ingest_pdf_body(body, final_url, title, tags, fetched_at, force)

    if not (
        any(content_type.startswith(t) for t in _HTML_TYPES)
        or any(content_type.startswith(t) for t in _TEXT_TYPES)
        or content_type == ""
    ):
        raise UrlIngestError(
            f"Unsupported content type '{content_type}'. Only HTML, plain text, and PDF are supported.",
            status_code=415,
        )

    text = extract_main_text(body, content_type)
    if not text.strip():
        raise UrlIngestError("No readable content could be extracted from the URL.", status_code=422)

    digest = content_hash(text)
    registry = _load_registry()
    existing = registry.get(final_url)

    if existing and existing.get("content_hash") == digest and not force:
        logger.info("URL unchanged since last ingest; skipping re-index: %s", final_url)
        return {
            "status": "unchanged",
            "url": final_url,
            "chunks_indexed": 0,
            "content_hash": digest,
            "fetched_at": fetched_at,
            "message": "Content unchanged since last ingestion; nothing re-indexed.",
        }

    base_metadata = {
        "source": final_url,
        "source_type": "url",
        "source_url": final_url,
        "title": title or final_url,
        "tags": tags,
        "fetched_at": fetched_at,
        "content_hash": digest,
    }
    documents = chunk_text(text, base_metadata)
    if not documents:
        raise UrlIngestError("Extracted content produced no chunks.", status_code=422)

    # Replace stale chunks for this URL before adding fresh ones.
    if existing and existing.get("ids"):
        try:
            vectorstore_manager.delete_documents(existing["ids"])
        except Exception as exc:
            logger.warning("Could not delete prior chunks for %s (%s); continuing", final_url, exc)

    ids = vectorstore_manager.add_documents(documents)
    logger.info("Indexed %d chunks from URL %s", len(documents), final_url)

    registry[final_url] = {
        "content_hash": digest,
        "ids": ids,
        "chunks": len(documents),
        "title": base_metadata["title"],
        "tags": tags,
        "fetched_at": fetched_at,
    }
    _save_registry(registry)

    return {
        "status": "reindexed" if existing else "indexed",
        "url": final_url,
        "title": base_metadata["title"],
        "tags": tags,
        "chunks_indexed": len(documents),
        "content_hash": digest,
        "fetched_at": fetched_at,
        "message": f"Indexed {len(documents)} chunks from the URL.",
    }


async def _ingest_pdf_body(
    body: bytes,
    final_url: str,
    title: Optional[str],
    tags: List[str],
    fetched_at: str,
    force: bool,
) -> Dict[str, Any]:
    """Persist a fetched PDF and run it through the existing document loader/chunker."""
    # Imported lazily to avoid a circular import (admin imports url_ingest indirectly).
    from .admin import UPLOAD_DIR, load_documents_from_file

    digest = hashlib.sha256(body).hexdigest()  # hash raw bytes for PDFs
    registry = _load_registry()
    existing = registry.get(final_url)
    if existing and existing.get("content_hash") == digest and not force:
        return {
            "status": "unchanged",
            "url": final_url,
            "chunks_indexed": 0,
            "content_hash": digest,
            "fetched_at": fetched_at,
            "message": "PDF unchanged since last ingestion; nothing re-indexed.",
        }

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
    safe_name = stamp + (urlparse(final_url).path.rsplit("/", 1)[-1] or "download")
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    pdf_path = UPLOAD_DIR / safe_name
    pdf_path.write_bytes(body)

    documents = load_documents_from_file(pdf_path)
    for doc in documents:
        doc.metadata.update(
            {
                "source_type": "url",
                "source_url": final_url,
                "title": title or final_url,
                "tags": tags,
                "fetched_at": fetched_at,
                "content_hash": digest,
            }
        )

    if existing and existing.get("ids"):
        try:
            vectorstore_manager.delete_documents(existing["ids"])
        except Exception as exc:
            logger.warning("Could not delete prior PDF chunks for %s (%s); continuing", final_url, exc)

    ids = vectorstore_manager.add_documents(documents)
    registry[final_url] = {
        "content_hash": digest,
        "ids": ids,
        "chunks": len(documents),
        "title": title or final_url,
        "tags": tags,
        "fetched_at": fetched_at,
        "saved_as": safe_name,
    }
    _save_registry(registry)
    logger.info("Indexed %d chunks from PDF URL %s", len(documents), final_url)

    return {
        "status": "reindexed" if existing else "indexed",
        "url": final_url,
        "title": title or final_url,
        "tags": tags,
        "chunks_indexed": len(documents),
        "content_hash": digest,
        "fetched_at": fetched_at,
        "saved_as": safe_name,
        "message": f"Indexed {len(documents)} chunks from the PDF.",
    }
