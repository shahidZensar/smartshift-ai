from datetime import datetime
import json

from .. import logger
from .. decision import openai_llm
from ..util import final_prompt, with_history
from ..prompts import HYBRID_PROMPT, STRUCTURED_PROMPT

# Function to chunk JSON into smaller batches
def chunk_json(data, batch_size=2):
    for i in range(0, len(data), batch_size):
        yield data[i:i+batch_size]

# Simulated "model response" function
# In practice, you would call your small model here
def process_batch(batch,rag_context,request):
    summaries = []
    for record in batch:
        final_chain_response = final_chain(sql_context=json.dumps(record, indent=2), rag_context=rag_context, request=request)
        summaries.append(final_chain_response)  # Collect the response for this record
    return summaries

# Full pipeline: process all batches and merge results
def process_full_payload(data, rag_context={},request=None, batch_size=2):
    all_summaries = []
    data = json.loads(data) if isinstance(data, str) else data
    logger.info("Data received for final chain processing: %r", isinstance(data, list))
    for batch in chunk_json(data, batch_size):
        batch_result = process_batch(batch, rag_context, request=request)
        all_summaries.extend(batch_result)
    return all_summaries

def final_chain(sql_context, rag_context, request, history: str = ""):
    final_response = ""
    logger.info("Starting final chain processing with SQL context and RAG context")
    logger.info("Current date: %r", datetime.utcnow().strftime("%Y-%m-%d"))
    formatted_prompt = with_history(
        final_prompt.format(sql_context=sql_context,
                            rag_context=rag_context, question=request.question,
                            current_date=datetime.utcnow().strftime("%Y-%m-%d")),
        history,
    )
    #logger.info("Formatted prompt for final response generation: %r", formatted_prompt)
    try:
        response = openai_llm.invoke(formatted_prompt)
        final_response = response.content if hasattr(response, 'content') else response
        #logger.info("Final response generated successfully%r", final_response)
    except Exception as e:
        logger.error("Error generating final response: %s",   e)
    return final_response

def final_hybrid_chain(sql_context, rag_context, request):
    final_response = ""
    logger.info("Starting final chain processing with SQL context and RAG context")
    logger.info("Current date: %r", datetime.utcnow().strftime("%Y-%m-%d"))
    formatted_prompt = final_prompt.format(sql_context=sql_context, 
                                        rag_context=rag_context, question=request.question, 
                                        current_date=datetime.utcnow().strftime("%Y-%m-%d"))
    #logger.info("Formatted prompt for final response generation: %r", formatted_prompt)
    try:
        response = openai_llm.invoke(formatted_prompt)
        final_response = response.content if hasattr(response, 'content') else response
        #logger.info("Final response generated successfully%r", final_response)
    except Exception as e:
        logger.error("Error generating final response: %s",   e)
    return final_response

def final_structured_chain(sql_context, request):
    final_response = ""
    logger.info("Starting final chain processing with SQL context and RAG context")
    logger.info("Current date: %r", datetime.utcnow().strftime("%Y-%m-%d"))
    formatted_prompt = STRUCTURED_PROMPT.format(sql_context=sql_context, 
                                        question=request.question)
    #logger.info("Formatted prompt for final response generation: %r", formatted_prompt)
    try:
        response = openai_llm.invoke(formatted_prompt)
        final_response = response.content if hasattr(response, 'content') else response
        #logger.info("Final response generated successfully%r", final_response)
    except Exception as e:
        logger.error("Error generating final response: %s",   e)
    return final_response

def final_chain_async(sql_context, rag_context, request):
    return process_full_payload(sql_context, rag_context,request,batch_size=2)