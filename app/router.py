import json

from .decision import llm
from .prompts import INTENT_CLASSIFIER_PROMPT, ROUTER_PROMPT

# CONFIG is checked first so an explicit config-change request wins.
VALID_INTENTS = ("CONFIG", "HYBRID", "SQL", "RAG", "SEARCH")

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
    for intent in intents:
        if intent in text:
            return intent

    # Safe default: fall back to external web SEARCH when intent is unclear.
    return "SEARCH"
