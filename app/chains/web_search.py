import os

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from .. import logger
from ..prompts import WEBESEARCH_PROMPT
from ..decision import llm
from ..util import with_history

def web_search(query):
    # Replace with internal search proxy or SerpAPI
    logger.info("Performing web search for query: %r", query)
    url = "https://serpapi.com/search"
    params = {"q": query, "api_key": '4e3379351b43635d0a2f402b14f3b0ba8c056b8664e2acc49449219bb6ea0cc9'}
    verify_ssl = os.getenv("SERPAPI_VERIFY_SSL", "false").strip().lower() in {"1", "true", "yes"}

    try:
        if not verify_ssl:
            disable_warnings(InsecureRequestWarning)

        response = requests.get(url, params=params, timeout=20, verify=verify_ssl)
        response.raise_for_status()
        return response.json().get("organic_results", [])
    except Exception as exc:
        logger.error("Web search failed, returning empty results: %s", exc)
        return []

def web_search_chain(query, history: str = ""):
    search_results = web_search(query)
    prompt = with_history(WEBESEARCH_PROMPT.format(query=query, search_results=search_results), history)
    llm_response = llm.invoke(prompt)
    return llm_response.content if hasattr(llm_response, 'content') else llm_response
