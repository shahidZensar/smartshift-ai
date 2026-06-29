from .. import logger
from ..decision import llm
from ..rag import vectorstore_manager
from ..prompts import RAG_PROMPT
from ..util import with_history


def rag_chain(query: str, history: str = "") -> str:
    """Retrieve relevant documents for the query and generate a context-grounded answer."""
    logger.info("Starting RAG chain for query: %r", query)

    rag_context = vectorstore_manager.retrieve_docs(query)
    if not rag_context:
        logger.warning("No RAG context retrieved; answering without document context")
        rag_context = "No relevant documents found."

    prompt = with_history(RAG_PROMPT.format(rag_context=rag_context, question=query), history)
    response = llm.invoke(prompt)
    return response.content if hasattr(response, 'content') else response
