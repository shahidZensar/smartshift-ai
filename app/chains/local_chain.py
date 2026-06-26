"""
Local LLM workflow — Ollama gemma4:latest + nomic-embed-text:latest.

Mirrors the full Azure workflow (intent → SQL / RAG / HYBRID / SEARCH) but
uses local_llm and local_vectorstore_manager throughout.  No Azure / OpenAI
calls are made anywhere in this module.
"""

import json
from datetime import datetime

import pandas as pd
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy import create_engine

from langchain_core.prompts import PromptTemplate

from .. import logger
from ..decision import local_llm
from ..rag import local_vectorstore_manager, vectorstore_manager
from ..prompts import INTENT_CLASSIFIER_PROMPT, WEBESEARCH_PROMPT
from ..util import (
    safe_text, sql_prompt, final_prompt, format_sql_response, with_history, table_info,
)
from ..config import MYSQL_URI

# ---------------------------------------------------------------------------
# Local-specific SQL prompt — identical to sql_prompt but adds:
#   rule 13: single-keyword LIKE patterns (gemma4 tends to use phrases)
#   extra example: "catalyst switches" → %%Catalyst%%
# ---------------------------------------------------------------------------
_local_sql_prompt = PromptTemplate(
    input_variables=["input", "table_info", "top_k", "current_date"],
    template=sql_prompt.template.replace(
        "12. Output: Two lines only - QUERY and PARAMS",
        (
            "12. Output: Two lines only - QUERY and PARAMS\n"
            "13. LIKE KEYWORD RULE: Each LIKE param must be a SINGLE KEY WORD — never a phrase.\n"
            "    CORRECT: %%Catalyst%%     WRONG: %%Catalyst switches%%\n"
            "    CORRECT: %%router%%       WRONG: %%routers and switches%%\n"
            "    CORRECT: %%WS-C3850%%     WRONG: %%Cisco Catalyst 3850%%\n"
            "    Extract the main product-family word only."
        ),
    ).replace(
        'Request: "which devices will support 4g feature?"',
        (
            'Request: "List catalyst switches"\n'
            "QUERY: SELECT * FROM inventory i WHERE i.product_description LIKE %s LIMIT {top_k}\n"
            "PARAMS: %%Catalyst%%\n\n"
            'Request: "which devices will support 4g feature?"'
        ),
    ),
)

# Reuse the web_search HTTP helper (no LLM, just SerpAPI)
from .web_search import web_search


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _text(response) -> str:
    """Normalize any LLM response to a plain string."""
    return response.content if hasattr(response, "content") else str(response)


_PROVIDED_CONTEXT_CUES = (
    "from the context", "from context", "provided context", "in the context",
    "from the document", "from the doc", "from the documents", "from the uploaded",
    "uploaded document", "uploaded content", "uploaded file", "from the file",
    "from the knowledge base", "knowledge base", "from the ingested",
    "i have provided", "i provided", "i have uploaded", "i uploaded",
)


def _references_provided_context(query: str) -> bool:
    q = (query or "").lower()
    return any(cue in q for cue in _PROVIDED_CONTEXT_CUES)


# ---------------------------------------------------------------------------
# 1. Intent classification
# ---------------------------------------------------------------------------

_VALID_INTENTS = ("CONFIG", "HYBRID", "SQL", "RAG", "SEARCH")


def local_classify_intent(query: str, history: str = "") -> str:
    """Classify query intent using local_llm (same prompt as Azure path)."""
    if local_llm is None:
        raise RuntimeError("Local LLM (Ollama) is not available.")

    prompt = INTENT_CLASSIFIER_PROMPT.format(query=query, history=history or "(none)")
    raw = _text(local_llm.invoke(prompt)).strip().upper()
    logger.info("Local intent raw LLM output: %r", raw)

    # Both SQL and RAG → HYBRID
    if "SQL" in raw and "RAG" in raw:
        return "HYBRID"

    for intent in _VALID_INTENTS:
        if intent in raw:
            # RAG-only safeguard: upgrade SEARCH → RAG when query references ingested context
            if intent == "SEARCH" and _references_provided_context(query):
                logger.info("Local intent override SEARCH → RAG (references provided context)")
                return "RAG"
            return intent

    # Safe default
    if _references_provided_context(query):
        return "RAG"
    logger.info("Local intent: no match found, defaulting to SEARCH")
    return "SEARCH"


# ---------------------------------------------------------------------------
# 2. SQL generation + DB execution
# ---------------------------------------------------------------------------

async def local_sql_chain(request, history: str = "") -> str:
    """Generate SQL via local_llm, execute against MySQL, return JSON records."""
    if local_llm is None:
        raise RuntimeError("Local LLM (Ollama) is not available.")

    current_date = pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
    raw_sql = await local_llm.ainvoke(
        with_history(
            _local_sql_prompt.format(
                input=safe_text(request.question),
                table_info=table_info,
                top_k=3,
                current_date=current_date,
            ),
            history,
        )
    )
    sql_query = StrOutputParser().parse(_text(raw_sql))
    logger.info("Local SQL: generated query raw: %r", sql_query)

    query, params = format_sql_response(sql_query)
    logger.info("Local SQL: parsed query=%r  params=%r", query, params)

    if not query:
        return "No data found matching the criteria."

    try:
        engine = create_engine(MYSQL_URI)
        query = query.replace("%d-%b-%Y", "%%d-%%b-%%Y")
        df = pd.read_sql(query, engine, params=params)
        df[df.select_dtypes(include="number").columns] = (
            df.select_dtypes(include="number").fillna(0).astype("Int64")
        )
        today = pd.Timestamp.now().normalize()
        df["eol"] = df.apply(
            lambda row: (
                (pd.Timestamp(row["last_date_of_support"]) - today).days
                if pd.notnull(row.get("last_date_of_support"))
                else (
                    (pd.Timestamp(row["end_date"]) - today).days
                    if pd.notnull(row.get("end_date"))
                    else None
                )
            ),
            axis=1,
        )
        date_cols = df.select_dtypes(include=["datetime", "datetimetz"]).columns
        df[date_cols] = df[date_cols].apply(lambda x: x.dt.strftime("%Y-%m-%d"))
        logger.info("Local SQL: executed, %d rows returned", len(df))
        if len(df) > 0:
            return df.to_json(orient="records", date_format="iso")
        return "No data found matching the criteria."
    except Exception as e:
        logger.error("Local SQL execution error: %s", e)
        return "No data found matching the criteria."


# ---------------------------------------------------------------------------
# 3. Response generation chains
# ---------------------------------------------------------------------------

from ..prompts import STRUCTURED_PROMPT


def local_final_sql_chain(sql_ctx: str, request) -> str:
    """SQL-only response (mirrors final_structured_chain but uses local_llm)."""
    if local_llm is None:
        raise RuntimeError("Local LLM (Ollama) is not available.")
    formatted = STRUCTURED_PROMPT.format(sql_context=sql_ctx, question=request.question)
    return _text(local_llm.invoke(formatted))


def local_final_chain(sql_ctx: str, rag_ctx: str, request, history: str = "") -> str:
    """HYBRID response (SQL + RAG) using local_llm (mirrors final_chain)."""
    if local_llm is None:
        raise RuntimeError("Local LLM (Ollama) is not available.")
    formatted = with_history(
        final_prompt.format(
            sql_context=sql_ctx,
            rag_context=rag_ctx,
            question=request.question,
            current_date=datetime.utcnow().strftime("%Y-%m-%d"),
        ),
        history,
    )
    return _text(local_llm.invoke(formatted))


# ---------------------------------------------------------------------------
# 4. RAG chain
# ---------------------------------------------------------------------------

_RAG_TMPL = (
    "You are an enterprise network device migration assistant.\n\n"
    "Knowledge Base Context:\n{rag_context}\n\n"
    "Conversation History:\n{history}\n\n"
    "User Question: {question}\n\n"
    "Instructions:\n"
    "- Answer using ONLY the provided context and conversation history.\n"
    "- If the context does not contain the answer, clearly state that.\n"
    "- Be concise and factual. Do not invent device models, EOL dates, or firmware versions.\n"
)


def _retrieve_rag(query: str, k: int = 5) -> str:
    """Retrieve docs from local index; fall back to shared index when local is empty."""
    ctx = local_vectorstore_manager.retrieve_docs(query, k=k)
    if ctx:
        return ctx
    # Local index not yet built — use shared (Azure-embedded) store for retrieval.
    # Generation still runs on local_llm; only the similarity search is shared.
    logger.info("Local RAG: local index empty, falling back to shared vectorstore for retrieval")
    return vectorstore_manager.retrieve_docs(query, k=k) or "No relevant documents found."


def local_rag_chain(query: str, history: str = "") -> str:
    if local_llm is None:
        raise RuntimeError("Local LLM (Ollama) is not available.")
    logger.info("Local RAG chain — query: %r", query)
    rag_ctx = _retrieve_rag(query)
    logger.info("Local RAG context length: %d chars", len(rag_ctx))
    return _text(local_llm.invoke(
        _RAG_TMPL.format(rag_context=rag_ctx, history=history or "None", question=query)
    ))


# ---------------------------------------------------------------------------
# 5. Web search chain
# ---------------------------------------------------------------------------

def local_web_search_chain(query: str, history: str = "") -> str:
    if local_llm is None:
        raise RuntimeError("Local LLM (Ollama) is not available.")
    results = web_search(query)
    if not results:
        # SERPAPI not configured or request failed — fall back to local RAG so the
        # user gets a grounded answer from the knowledge base instead of an empty prompt.
        logger.warning("Web search returned no results; falling back to local RAG for query: %r", query)
        return local_rag_chain(query, history)
    prompt = with_history(
        WEBESEARCH_PROMPT.format(query=query, search_results=results), history
    )
    return _text(local_llm.invoke(prompt))


# ---------------------------------------------------------------------------
# 6. Full local workflow entry point
# ---------------------------------------------------------------------------

async def local_full_chat(request, history: str = "", session_id: str = "") -> tuple:
    """
    Complete local workflow: classify intent → execute the matching chain.
    Returns (answer: str, intent: str, config_payload: dict | None).
    config_payload is only set when intent == 'CONFIG'; None otherwise.
    """
    if local_llm is None:
        raise RuntimeError(
            "Local LLM (Ollama gemma4:latest) is not available. "
            "Ensure Ollama is running (`ollama serve`) and gemma4 is pulled."
        )

    question = request.question
    intent = local_classify_intent(question, history)
    logger.info("Local full chat — intent=%r  query=%r", intent, question)

    if intent == "CONFIG":
        from ..services.config_service import config_service
        # Use the caller-resolved session_id (which may be a generated UUID) so
        # CONFIG state is stored under the same key that gets returned to the client.
        sid = session_id or request.session_id or ""
        config_payload = config_service.handle(
            request.question,
            sid,
            form_values=getattr(request, "form_values", None),
            llm=local_llm,
        )
        if config_payload.get("route") == "NOT_CONFIG":
            # Semantic gate decided this isn't a real config action — fall back to SEARCH
            logger.info("Local CONFIG: NOT_CONFIG returned by semantic gate, falling back to SEARCH")
            answer = local_web_search_chain(question, history)
            return answer, "SEARCH", None
        return config_payload.get("answer", ""), "CONFIG", config_payload

    elif intent == "SQL":
        sql_ctx = await local_sql_chain(request, history)
        answer = local_final_sql_chain(sql_ctx, request)

    elif intent == "RAG":
        answer = local_rag_chain(question, history)

    elif intent == "HYBRID":
        sql_ctx = await local_sql_chain(request, history)
        # Narrow the RAG query to the actual device family (mirrors Azure HYBRID path)
        rag_query = question
        try:
            rows = json.loads(sql_ctx)
            descs = "; ".join(sorted({
                str(r.get("product_description", "")).lstrip("^").strip()
                for r in rows if r.get("product_description")
            }))
            if descs:
                rag_query = f"replacement product datasheet and upgrade guidance for: {descs}"
        except Exception:
            pass
        rag_ctx = _retrieve_rag(rag_query, k=8)
        answer = local_final_chain(sql_ctx, rag_ctx, request, history)

    elif intent == "SEARCH":
        answer = local_web_search_chain(question, history)

    else:
        answer = local_rag_chain(question, history)
        intent = "RAG"

    return answer, intent, None
