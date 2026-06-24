"""
Tests for the hardened URL ingestion pipeline (app/url_ingest.py).

Covers: SSRF rejection, content extraction, chunk/embed/upsert (mocked vector
store), and content-hash idempotency. Network and embeddings are fully mocked,
so these run offline.

Run from the `temp/app` directory's parent:  pytest app/tests/test_url_ingest.py
"""
import pytest

from app import url_ingest
from app.url_ingest import (
    UrlIngestError,
    validate_public_url,
    extract_main_text,
    chunk_text,
    content_hash,
    ingest_url,
)


# --------------------------------------------------------------------------
# SSRF protection
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_url",
    [
        "ftp://example.com/file",            # disallowed scheme
        "file:///etc/passwd",                 # disallowed scheme
        "http://127.0.0.1/admin",             # loopback
        "http://localhost/admin",             # loopback (resolves to 127.0.0.1)
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (link-local)
        "http://10.0.0.5/internal",           # private
        "http://192.168.1.1/router",          # private
        "http://[::1]/x",                      # ipv6 loopback
        "https://example.com:8080/x",         # disallowed port
        "https:///nohost",                     # no host
    ],
)
def test_validate_public_url_rejects_unsafe(bad_url):
    with pytest.raises(UrlIngestError):
        validate_public_url(bad_url)


def test_validate_public_url_accepts_public_ip_literal():
    # Public IP literal needs no DNS and must pass.
    assert validate_public_url("https://8.8.8.8/") == "https://8.8.8.8/"


def test_validate_public_url_accepts_public_host(monkeypatch):
    # Resolve a hostname to a public address -> allowed.
    monkeypatch.setattr(
        url_ingest.socket,
        "getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert validate_public_url("https://example.com/page").startswith("https://example.com")


def test_validate_public_url_rejects_dns_to_private(monkeypatch):
    # A public hostname that resolves to a private IP (DNS-rebinding style) is rejected.
    monkeypatch.setattr(
        url_ingest.socket,
        "getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("10.1.2.3", 0))],
    )
    with pytest.raises(UrlIngestError):
        validate_public_url("https://evil.example.com/")


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def test_extract_main_text_strips_boilerplate():
    html = b"""
    <html><head><title>T</title><style>.x{}</style></head>
    <body>
      <nav>HOME ABOUT</nav>
      <script>var a=1;</script>
      <article><p>The important readable content lives here.</p></article>
      <footer>copyright</footer>
    </body></html>
    """
    text = extract_main_text(html, "text/html")
    assert "important readable content" in text
    # script contents must never survive extraction.
    assert "var a=1" not in text


def test_extract_main_text_plain():
    assert extract_main_text(b"just text", "text/plain") == "just text"


def test_chunk_text_attaches_metadata():
    docs = chunk_text("word " * 800, {"source_type": "url", "source_url": "u"})
    assert len(docs) >= 1
    assert docs[0].metadata["source_type"] == "url"
    assert docs[0].metadata["chunk_index"] == 0


# --------------------------------------------------------------------------
# Orchestration: chunk -> upsert + idempotency
# --------------------------------------------------------------------------
class FakeVectorStore:
    def __init__(self):
        self.added = []
        self.deleted = []
        self._counter = 0

    def add_documents(self, documents, ids=None):
        self.added.append(documents)
        ids = ids or [f"id-{self._counter + i}" for i in range(len(documents))]
        self._counter += len(documents)
        return ids

    def delete_documents(self, ids):
        self.deleted.append(ids)
        return len(ids)


@pytest.fixture
def patched(monkeypatch, tmp_path):
    fake = FakeVectorStore()
    monkeypatch.setattr(url_ingest, "vectorstore_manager", fake)
    monkeypatch.setattr(url_ingest, "REGISTRY_PATH", tmp_path / "registry.json")
    # Skip SSRF/DNS in orchestration tests (covered separately above).
    monkeypatch.setattr(url_ingest, "validate_public_url", lambda u: u)

    html = b"<html><body><article><p>Hello indexed world. " + b"data " * 500 + b"</p></article></body></html>"

    async def fake_fetch(url):
        return html, "text/html", "https://site.test/doc"

    monkeypatch.setattr(url_ingest, "fetch_url", fake_fetch)
    return fake


@pytest.mark.asyncio
async def test_ingest_url_indexes_with_metadata(patched):
    summary = await ingest_url("https://site.test/doc", title="Doc", tags=["a", "b"])
    assert summary["status"] == "indexed"
    assert summary["chunks_indexed"] >= 1
    # Upsert happened with url metadata on each chunk.
    docs = patched.added[0]
    assert docs[0].metadata["source_type"] == "url"
    assert docs[0].metadata["source_url"] == "https://site.test/doc"
    assert docs[0].metadata["title"] == "Doc"
    assert docs[0].metadata["tags"] == ["a", "b"]
    assert "content_hash" in docs[0].metadata


@pytest.mark.asyncio
async def test_ingest_url_is_idempotent(patched):
    first = await ingest_url("https://site.test/doc")
    assert first["status"] == "indexed"
    # Same content again -> skipped, no second upsert.
    second = await ingest_url("https://site.test/doc")
    assert second["status"] == "unchanged"
    assert second["chunks_indexed"] == 0
    assert len(patched.added) == 1


@pytest.mark.asyncio
async def test_ingest_url_force_replaces(patched):
    await ingest_url("https://site.test/doc")
    forced = await ingest_url("https://site.test/doc", force=True)
    assert forced["status"] == "reindexed"
    # Prior chunks deleted before re-adding.
    assert patched.deleted, "expected stale chunks to be deleted on forced re-index"
    assert len(patched.added) == 2


@pytest.mark.asyncio
async def test_ingest_url_rejects_unsupported_content_type(monkeypatch, tmp_path):
    monkeypatch.setattr(url_ingest, "REGISTRY_PATH", tmp_path / "r.json")
    monkeypatch.setattr(url_ingest, "validate_public_url", lambda u: u)

    async def fake_fetch(url):
        return b"\x00\x01binary", "image/png", url

    monkeypatch.setattr(url_ingest, "fetch_url", fake_fetch)
    with pytest.raises(UrlIngestError) as exc:
        await ingest_url("https://site.test/image.png")
    assert exc.value.status_code == 415


def test_content_hash_stable():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
