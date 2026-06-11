import json

from .decision import llm
from .prompts import INTENT_CLASSIFIER_PROMPT, ROUTER_PROMPT

VALID_INTENTS = ("HYBRID", "SQL", "RAG", "SEARCH")

def classify_intent(query):
    prompt = INTENT_CLASSIFIER_PROMPT.format(query=query)
    response = llm.invoke(prompt)
    raw = response.content if hasattr(response, 'content') else response
    text = str(raw).strip().upper()

    # Both SQL and RAG mentioned -> HYBRID. Otherwise match the first intent present.
    if "SQL" in text and "RAG" in text:
        return "HYBRID"
    for intent in VALID_INTENTS:
        if intent in text:
            return intent

    # Safe default: fall back to external web SEARCH when intent is unclear.
    return "SEARCH"

