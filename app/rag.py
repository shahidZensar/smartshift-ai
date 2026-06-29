import os
import time
import uuid

from . import logger
from langchain_community.vectorstores import FAISS
from .decision import embeddings
from .config import *

# Kept for backward compatibility with modules importing `vectorstore`/`FAISS` from here.
vectorstore = None

# Embedding ingestion settings (tunable; small batches stay under provider rate limits).
EMBED_BATCH_SIZE = 200
EMBED_MAX_RETRIES = 8
EMBED_RETRY_DELAY = 60  # seconds; Azure 429 responses ask to retry after ~60s

class VectorStoreManager:
    def __init__(self):
        self.vectorstore = None

    def _add_batch_with_retry(self, batch, batch_ids):
        """Embed+add one batch (with explicit ids), retrying on provider rate-limit (HTTP 429)."""
        for attempt in range(1, EMBED_MAX_RETRIES + 1):
            try:
                if not self.vectorstore:
                    self.vectorstore = FAISS.from_documents(batch, embeddings, ids=batch_ids)
                else:
                    self.vectorstore.add_documents(batch, ids=batch_ids)
                return
            except Exception as e:
                msg = str(e)
                is_rate_limited = "429" in msg or "rate limit" in msg.lower() or "RateLimit" in msg
                if is_rate_limited and attempt < EMBED_MAX_RETRIES:
                    logger.warning(
                        "Embedding rate-limited (attempt %d/%d); sleeping %ds then retrying",
                        attempt, EMBED_MAX_RETRIES, EMBED_RETRY_DELAY
                    )
                    time.sleep(EMBED_RETRY_DELAY)
                    continue
                raise

    def add_documents(self, documents, ids=None):
        """Index documents in batches and persist. Raises on persistent failure
        (no longer swallows errors, so callers/uploads see real failures).

        Returns the list of vector ids assigned to the documents so callers can
        later delete/replace them (used for idempotent URL re-indexing). When
        `ids` is not supplied, fresh uuids are generated."""
        if not documents:
            logger.warning("add_documents called with no documents")
            return []
        total = len(documents)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(total)]
        elif len(ids) != total:
            raise ValueError("ids length (%d) must match documents length (%d)" % (len(ids), total))
        logger.info("Indexing %d documents in batches of %d", total, EMBED_BATCH_SIZE)
        try:
            for start in range(0, total, EMBED_BATCH_SIZE):
                batch = documents[start:start + EMBED_BATCH_SIZE]
                batch_ids = ids[start:start + EMBED_BATCH_SIZE]
                self._add_batch_with_retry(batch, batch_ids)
                self.save_vectorstore(RAG_INDEX_PATH)  # persist incrementally
                logger.info("Indexed %d/%d documents", min(start + EMBED_BATCH_SIZE, total), total)
            logger.info("Finished indexing %d documents", total)
            return ids
        except Exception as e:
            logger.error("Failed to index documents: %s", str(e))
            raise

    def delete_documents(self, ids):
        """Remove previously-indexed chunks by id and persist. No-op if the store
        is empty or `ids` is falsy. Used to replace stale URL content on re-fetch."""
        if not ids:
            return 0
        if not self.vectorstore:
            logger.warning("delete_documents called but vector store is not initialized")
            return 0
        try:
            self.vectorstore.delete(ids)
            self.save_vectorstore(RAG_INDEX_PATH)
            logger.info("Deleted %d chunks from vector store", len(ids))
            return len(ids)
        except Exception as e:
            logger.error("Failed to delete documents: %s", str(e))
            raise

    def search(self, query, k=RAG_TOP_K):
        return self.vectorstore.similarity_search(query, k=k) if self.vectorstore else []

    def retrieve_docs(self, query, k=RAG_TOP_K):
        if not self.vectorstore:
            logger.warning("Vector store not initialized; cannot retrieve documents")
            return ""
        try:
            docs = self.vectorstore.similarity_search(query, k=k)
            logger.info("Retrieved %d documents for query", len(docs))
            return "\n\n".join(d.page_content for d in docs)
        except Exception as e:
            logger.error("Error retrieving documents: %s", e)
            return ""

    def save_vectorstore(self, path):
        # Use FAISS.save_local so the docstore + id mapping are persisted alongside
        # the index (faiss.write_index only saves the raw index and loses documents).
        if self.vectorstore:
            self.vectorstore.save_local(path)
            logger.info(f"Vector store saved to {path}")
        else:
            logger.warning("No vector store to save")

    def load_vectorstore(self, path):
        # FAISS.save_local writes index.faiss + index.pkl inside `path`.
        if not os.path.isdir(path) or not os.path.exists(os.path.join(path, "index.faiss")):
            logger.warning(
                "No FAISS index found at %r; vector store left uninitialized "
                "(upload documents via /api/admin/upload-file to build it)", path
            )
            self.vectorstore = None
            return
        try:
            self.vectorstore = FAISS.load_local(
                path, embeddings, allow_dangerous_deserialization=True
            )
            logger.info(
                "Vector store loaded from %s (%d vectors)",
                path, self.vectorstore.index.ntotal
            )
        except Exception as e:
            logger.error(f"Error loading vector store: {str(e)}")
            self.vectorstore = None

    @staticmethod
    def check_sufficiency(query, docs):
        class SufficiencyResult:
            def __init__(self, action):
                self.action = action
        # Example logic: if docs is not empty, return ANSWER, else return SEARCH_WEB
        return SufficiencyResult("ANSWER" if docs else "SEARCH_WEB")


vectorstore_manager = VectorStoreManager()


# ========== LOCAL VECTOR STORE (Ollama nomic-embed-text) ==========
# Separate FAISS index built with local embeddings; stored at data/rag_index_local.
# If Ollama is not running (local_embeddings is None), all methods degrade gracefully.
_LOCAL_RAG_INDEX_PATH = os.path.join(BASE_DIR, "data", "rag_index_local")


class LocalVectorStoreManager:
    """FAISS vector store that uses Ollama (nomic-embed-text) for embeddings."""

    def __init__(self):
        self.vectorstore = None

    def _get_embeddings(self):
        from .decision import local_embeddings as _le
        if _le is None:
            raise RuntimeError(
                "Local embeddings (Ollama nomic-embed-text) are not available. "
                "Make sure Ollama is running: `ollama serve`"
            )
        return _le

    def add_documents(self, documents, ids=None):
        if not documents:
            logger.warning("local add_documents called with no documents")
            return []
        emb = self._get_embeddings()
        total = len(documents)
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in range(total)]
        for start in range(0, total, EMBED_BATCH_SIZE):
            batch = documents[start:start + EMBED_BATCH_SIZE]
            batch_ids = ids[start:start + EMBED_BATCH_SIZE]
            if not self.vectorstore:
                self.vectorstore = FAISS.from_documents(batch, emb, ids=batch_ids)
            else:
                self.vectorstore.add_documents(batch, ids=batch_ids)
            self.vectorstore.save_local(_LOCAL_RAG_INDEX_PATH)
            logger.info("Local index: indexed %d/%d documents", min(start + EMBED_BATCH_SIZE, total), total)
        return ids

    def retrieve_docs(self, query, k=RAG_TOP_K):
        if not self.vectorstore:
            self._try_load()
        if not self.vectorstore:
            logger.warning("Local vector store not initialized; returning empty context")
            return ""
        try:
            docs = self.vectorstore.similarity_search(query, k=k)
            return "\n\n".join(d.page_content for d in docs)
        except Exception as e:
            logger.error("Local vector store retrieval error: %s", e)
            return ""

    def _try_load(self):
        index_faiss = os.path.join(_LOCAL_RAG_INDEX_PATH, "index.faiss")
        if not os.path.exists(index_faiss):
            return
        try:
            emb = self._get_embeddings()
            self.vectorstore = FAISS.load_local(
                _LOCAL_RAG_INDEX_PATH, emb, allow_dangerous_deserialization=True
            )
            logger.info("Local vector store loaded (%d vectors)", self.vectorstore.index.ntotal)
        except Exception as e:
            logger.error("Failed to load local vector store: %s", e)
            self.vectorstore = None


local_vectorstore_manager = LocalVectorStoreManager()
