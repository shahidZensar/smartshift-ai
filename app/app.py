import json
import uuid
import uvicorn
import torch

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, File, UploadFile, Form, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from typing import List, Optional
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from langchain_core.output_parsers import StrOutputParser
from langchain_classic.chains.sql_database.query import create_sql_query_chain


from .file_analyzer import extract_device_info, build_query_from_device
from .models import HealthResponse, LLMResponse, QueryRequest, QueryResponse
from . import logger
from .decision import route_query, check_sufficiency, llm, sql_llm, llm_chat, openai_llm
from .rag import vectorstore_manager
from .memory import store_document, retrieve_memory
from .config import CONVERSTIONAL_MEMORY_PROMPT, MYSQL_URI, RAG_INDEX_PATH
from .admin import admin_router
from .util import final_prompt
from .chains.sql_chain import sql_chain
from .chains.response_chain import final_chain_async, final_chain, final_structured_chain
from .chains.web_search import web_search, web_search_chain
from .chains.rag_chain import rag_chain
from .router import classify_intent
from .services.conversation_store import conversation_store
from .services.config_service import config_service
from .models import ConfigStage

torch.set_default_tensor_type(torch.cuda.FloatTensor if torch.cuda.is_available() else torch.FloatTensor)

app = FastAPI(title="SmarAI API", version="1.0", description="API for SmarAI device lifecycle and licensing information")

base_app = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)    

@base_app.get("/health")
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0"
    )

@base_app.post("/chat/upload", response_model=QueryResponse)
async def chat_with_files(
    question: str = Form(...),
    session_id: Optional[str] = Form(None),
    include_context: Optional[bool] = Form(True),
    files: List[UploadFile] = File(default=[])
):
    """
    Chat endpoint that accepts files
    Processes uploaded files along with the question
    """
    try:
        query = {}
        file: Optional[UploadFile] = files[0] if files else None
        logger.info(f"Received question: {question}")
        file_attached = files[0].filename if files else "No file attached"
        logger.info(f"File attached: {file_attached}")
        decision = route_query(question, file_attached)
        logger.info(f"Processing file: {file.filename if file else 'None'} with decision: {decision.action}")
        if decision.action == "ANALYZE_FILE" and file:
            content = (await file.read()).decode()
            logger.info(f"Extracted content from file: {content[:100]}...")  # Log first 100 chars
            store_document(session_id, content)
            return QueryResponse (
                answer="File stored in session memory. You can now ask questions.",
                session_id=session_id,
                sources=[file.filename] if file and file.filename is not None else [],
                follow_up_questions=[]
            )
 
        # --- RAG SEARCH ---
        if decision.action in ["SEARCH_RAG", "ANALYZE_FILE"]:
            docs = vectorstore_manager.retrieve_docs(question)

            sufficiency = check_sufficiency(question, docs)

            if sufficiency.action == "ANSWER":
                return {
                    "query": question,
                    "source": "internal_rag",
                    "context": docs[:2000]
                }
            else:
                web_data = web_search(question)
                return {
                    "query": question,
                    "source": "web_fallback",
                    "context": web_data[:2000]
                }

        # --- DIRECT ANSWER ---
        if decision.action == "DIRECT_ANSWER":
            return {"message": "Use LLM direct answer here."}

        if decision.action == "CLARIFY":
            return {"message": "Please provide device model and version."}

        if decision.action == "REFUSE":
            return {"message": "Request out of scope."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat with files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )

@app.post("/api/chat", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """
    Main chat endpoint - processes user questions using RAG
    
    - **question**: User's question
    - **session_id**: Optional session ID for conversation tracking
    - **include_context**: Whether to include retrieved context
    """
    memory_context = {}
    rag_context = {}
    formatted_prompt = ""
    try:
        # Validate question is not empty
        if not request.question or not request.question.strip():
            raise HTTPException(
                status_code=400,
                detail="Question cannot be empty"
            )
        
        logger.info(f"Received question: {request.question}")

        if request.session_id:
            logger.info("Session ID: %r", request.session_id)
            memory_context =retrieve_memory(request.session_id, request.question)
            # Generate response using RAG
            formatted_prompt = CONVERSTIONAL_MEMORY_PROMPT.format(
                memory_context=memory_context,
                rag_context="RAG context goes here",
                query=request.question
            ) 
        else:
            rag_context = vectorstore_manager.retrieve_docs(request.question)  
            formatted_prompt = request.question    
        response = llm.invoke(formatted_prompt)
        response = StrOutputParser().parse(response)
        # Create query response
        query_response = QueryResponse(
            answer=response,
            session_id=request.session_id,
            sources=[],
            follow_up_questions=[]
        )
        
        logger.info(f"Generated response successfully")
        return query_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing question: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing question: {str(e)}"
        )

@app.post("/api/v1/chat", response_model=QueryResponse)
async def askv1_question(request: QueryRequest):
    """
    Main chat endpoint - processes user questions using RAG
    
    - **question**: User's question
    - **session_id**: Optional session ID for conversation tracking
    - **include_context**: Whether to include retrieved context
    """
    sql_context: str = "No SQL context available."
    rag_context = {}
    response = None
    try:
        # Validate question is not empty
        if not request.question or not request.question.strip():
            raise HTTPException(
                status_code=400,
                detail="Question cannot be empty"
            )
        logger.info(f"Received question: {request.question}")

        # --- session + chaining (req #1) ---
        session_id = request.session_id or str(uuid.uuid4())
        history_str = conversation_store.format_recent(session_id)

        # Resume an in-progress CONFIG conversation without re-classifying.
        active_cfg = conversation_store.get_config_state(session_id)
        config_in_progress = active_cfg is not None and active_cfg.stage != ConfigStage.DONE

        if config_in_progress:
            tool = "CONFIG"
        else:
            tool = classify_intent(request.question, history_str)
        logger.info(f"Classified intent: {tool}")

        # --- CONFIG intent: stateful refinement loop (see CONFIG_INTENT_PLAN.md) ---
        if tool.strip() == "CONFIG":
            config_payload = config_service.handle(
                request.question, session_id, form_values=getattr(request, "form_values", None)
            )
            if config_payload.get("route") == "NOT_CONFIG":
                # Semantic gate decided this isn't a configuration action after all.
                # Hand control back to the normal router (CONFIG excluded so it can't
                # bounce straight back) and fall through to the existing intent handling.
                # SQL / RAG / SEARCH / HYBRID paths below are completely unaffected.
                tool = classify_intent(request.question, history_str, allow_config=False)
                logger.info("CONFIG gate returned NOT_CONFIG; re-routed to %r", tool)
            else:
                conversation_store.append_turn(session_id, "user", request.question)
                conversation_store.append_turn(session_id, "assistant", config_payload.get("answer", ""))
                content = {
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "sources": [],
                    "follow_up_questions": [],
                }
                content.update(config_payload)
                return JSONResponse(status_code=200, content=content)

        if tool.strip() == "SQL":
            sql_context = await sql_chain(request, history_str)
            logger.info(f"Processing question: {request.question}")
            logger.info("SQL context length:%r", sql_context)
            response = final_structured_chain(sql_context, request)
        elif tool.strip() == "RAG":
            logger.info(f"Processing question with RAG: {request.question}")
            response = rag_chain(request.question, history_str)
        elif tool.strip() == "HYBRID":
            sql_context = await sql_chain(request, history_str)
            logger.info(f"Processing question: {request.question}")
            try:
                rag_context = vectorstore_manager.retrieve_docs(request.question)
            except Exception as e:
              logger.error("Error retrieving RAG context: %s",   e)
            logger.info("Preparing final prompt and invoking llm")  # Log first 100 chars of SQL context
            logger.info("SQL context length:%r", sql_context)
            #response = final_chain_async(sql_context, rag_context, request)
            response = final_chain(sql_context, rag_context, request, history_str)
        elif tool.strip() == "SEARCH" :
             logger.info(f"Processing question with web search: {request.question}")
             response = web_search_chain(request.question, history_str)
             #response = "Web search results go here"
        answer_text = "".join(response) if isinstance(response, list) else str(response)
        conversation_store.append_turn(session_id, "user", request.question)
        conversation_store.append_turn(session_id, "assistant", answer_text)
        logger.info(f"Generated response successfully:%r", response)
        return JSONResponse(
            status_code=200,
            content={
                "answer": answer_text,
                "session_id": session_id,
                "intent": tool.strip(),
                "timestamp": datetime.utcnow().isoformat(),
                "sources": [],
                "follow_up_questions": []
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing question: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing question: {str(e)}"
        )    
# ==================== Error Handlers ====================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with helpful messages"""
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": [
                {
                    "field": str(error["loc"]),
                    "message": error["msg"],
                    "type": error["type"]
                }
                for error in exc.errors()
            ],
            "example": {
                "question": "Your question here",
                "session_id": "optional-session-id",
                "include_context": True
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    logger.error(f"Unexpected error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# ==================== Startup/Shutdown Events ====================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("Device Chat API started")
    logger.info("RAG model and embeddings loaded successfully")
    vectorstore_manager.load_vectorstore(RAG_INDEX_PATH)
    # CONFIG intent: ensure the config_inventory table exists + has dummy data.
    try:
        from .config_inventory import ensure_schema_and_seed
        ensure_schema_and_seed()
    except Exception as exc:
        logger.warning("config_inventory seed skipped (%s); picker will use fallback", exc)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Device Chat API shutting down")

app.include_router(base_app)
app.include_router(admin_router)

if __name__ == "__main__":
    uvicorn.run("app.app:app", host="0.0.0.0", port=8000, reload=True, workers=1,
                 log_level="info", access_log=True)


