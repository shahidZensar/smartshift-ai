import json

from . import logger
from .decision import llm
from .prompts import INTENT_CLASSIFIER_PROMPT, ROUTER_PROMPT

# CONFIG is checked first so an explicit config-change request wins.
VALID_INTENTS = ("CONFIG", "HYBRID", "SQL", "RAG", "SEARCH")

# Explicit cues that the user wants the answer drawn from the content they ingested
# into the knowledge base (uploaded files or "Add Content from URL"). When any of
# these appear, a web SEARCH fallback is almost certainly wrong — the user is asking
# about THEIR context, which is RAG. Matched case-insensitively as substrings.
_PROVIDED_CONTEXT_CUES = (
    "from the context", "from context", "provided context", "in the context",
    "context i have provided", "context which i have provided", "context i provided",
    "based on the context", "given context", "using the context",
    "from the document", "from the doc", "in the document", "from the documents",
    "from the uploaded", "uploaded document", "uploaded content", "uploaded file",
    "from the file", "from the url", "from the page", "from the website",
    "from the knowledge base", "knowledge base", "from the ingested", "ingested content",
    "indexed content", "from the indexed", "i have provided", "i provided",
    "i have uploaded", "i uploaded", "that i added", "i have added", "i added",
)


def _references_provided_context(query: str) -> bool:
    """True if the query explicitly refers to user-provided / ingested context."""
    q = (query or "").lower()
    return any(cue in q for cue in _PROVIDED_CONTEXT_CUES)


def classify_intent(query, history="", allow_config=True):
    prompt = INTENT_CLASSIFIER_PROMPT.format(query=query, history=history or "(none)")
    response = llm.invoke(prompt)
    raw = response.content if hasattr(response, 'content') else response
    text = str(raw).strip().upper()

    # Both SQL and RAG mentioned -> HYBRID. Otherwise match the first intent present.
    if "SQL" in text and "RAG" in text:
        return "HYBRID"
    # allow_config=False is used only for the CONFIG semantic gate's NOT_CONFIG hand-back,
    # so a re-classification can't bounce straight back into CONFIG. Default behaviour
    # (and every non-CONFIG caller) is unchanged.
    intents = VALID_INTENTS if allow_config else tuple(i for i in VALID_INTENTS if i != "CONFIG")
    result = None
    for intent in intents:
        if intent in text:
            result = intent
            break
    if result is None:
        # Safe default: fall back to external web SEARCH when intent is unclear.
        result = "SEARCH"

    # RAG-only safeguard: if the model fell back to web SEARCH but the user explicitly
    # asked about the context/documents THEY provided or ingested, answer from the
    # internal knowledge base instead. This ONLY ever upgrades SEARCH -> RAG; SQL,
    # CONFIG, HYBRID and RAG verdicts are returned untouched.
    if result == "SEARCH" and _references_provided_context(query):
        logger.info("Intent override SEARCH -> RAG: query references provided/ingested context")
        return "RAG"

    return result
