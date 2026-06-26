#from langchain_community.llms import Ollama
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from .config import *
from .models import RoutingDecision, SufficiencyDecision
from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache
from langchain_openai import ChatOpenAI
from . import logger
import os

#set_llm_cache(InMemoryCache())

# ========== DYNAMIC LLM INITIALIZATION ==========

def create_llm_instance(provider=None, model=None, temperature=None, top_p=None, **kwargs):
    """
    Factory function to create LLM instance dynamically based on provider.
    
    Args:
        provider (str): Model provider - 'ollama', 'openai', 'localai', 'azure', 'llamacpp'
        model (str): Model name/ID
        temperature (float): Temperature for sampling
        top_p (float): Top-p for nucleus sampling
        **kwargs: Additional provider-specific arguments
        
    Returns:
        LLM instance from LangChain
        
    Raises:
        ValueError: If provider is not supported
    """
    # Use defaults from config if not provided
    provider = provider or MODEL_PROVIDER
    model = model or MODEL
    temperature = temperature if temperature is not None else TEMPERATURE
    top_p = top_p if top_p is not None else TOP_P
    
    logger.info("Creating LLM instance: provider=%r, model=%r, temperature=%r", provider, model, temperature)
    
    try:
        if provider.lower() == 'ollama':
            """Local Ollama instance"""
            llm_instance = OllamaLLM(
                model=model,
                base_url=BASE_URL,
                temperature=temperature,
                top_p=top_p,
            )
            logger.info("✓ Ollama LLM initialized: %s at %s", model, BASE_URL)
            
        elif provider.lower() == 'openai':
            """OpenAI GPT models"""
            api_key = kwargs.get('api_key') or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")
            
            llm_instance = ChatOpenAI(
                api_key=str(api_key),  # type: ignore
                model=model,
                temperature=temperature,
                top_p=top_p,
                timeout=kwargs.get('timeout', 600),
                base_url=kwargs.get('base_url', "https://api.openai.com/v1"),
                max_retries=kwargs.get('max_retries', 3),
            )
            logger.info("✓ OpenAI LLM initialized: %s", model)
            
        elif provider.lower() == 'localai':
            """LocalAI (OpenAI-compatible local server)"""
            base_url = kwargs.get('base_url') or os.getenv("LOCALAI_BASE_URL", "http://localhost:8080/v1")
            api_key = kwargs.get('api_key') or os.getenv("LOCALAI_API_KEY", "") or "not-needed"
            
            llm_instance = ChatOpenAI(
                api_key=str(api_key),  # type: ignore
                model=model,
                base_url=base_url,
                temperature=temperature,
                top_p=top_p,
                timeout=kwargs.get('timeout', 600),
                max_retries=kwargs.get('max_retries', 2),
            )
            logger.info("✓ LocalAI LLM initialized: %s at %s", model, base_url)
            
        elif provider.lower() == 'azure':
            """Azure OpenAI"""
            from langchain_openai import AzureChatOpenAI
            
            api_key = kwargs.get('api_key') or os.getenv("AZURE_OPENAI_API_KEY")
            if not api_key:
                raise ValueError("AZURE_OPENAI_API_KEY not found")
            
            llm_instance = AzureChatOpenAI(
                azure_endpoint=kwargs.get('azure_endpoint') or os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=str(api_key),  # type: ignore
                api_version=kwargs.get('api_version') or os.getenv("API_VERSION") or "2024-02-15-preview",
                model=model,
                temperature=temperature,
                top_p=top_p,
                timeout=kwargs.get('timeout', 600),
            )
            logger.info("✓ Azure OpenAI LLM initialized: %s", model)
            
        elif provider.lower() == 'llamacpp':
            """Llama CPP (LM Studio, llama.cpp server)"""
            from langchain_community.llms import LlamaCpp
            
            # Support both local file path and remote server
            host = kwargs.get('host') or os.getenv("LLAMACPP_HOST")
            port = kwargs.get('port') or os.getenv("LLAMACPP_PORT")
            model_path = kwargs.get('model_path') or os.getenv("LLAMACPP_MODEL_PATH")
            
            if host and port:
                # Remote llama.cpp server - use OllamaLLM (ChatOllama compatible)
                base_url = f"http://{host}:{port}"
                llm_instance = ChatOpenAI(
                    model=model,
                    base_url=base_url,
                    temperature=temperature,
                    top_p=top_p,
                    api_key="not-needed",  # No API key for local llama.cpp server
                    max_retries=kwargs.get('max_retries', 2),
                )
                logger.info("✓ Llama CPP remote server initialized: %s", base_url)
            elif model_path:
                # Local model file
                llm_instance = LlamaCpp(
                    model_path=model_path,
                    temperature=temperature,
                    top_p=top_p,
                    n_ctx=kwargs.get('n_ctx', 64000),
                    n_gpu_layers=kwargs.get('n_gpu_layers', -1),
                    n_threads=kwargs.get('n_threads', 8),
                    verbose=kwargs.get('verbose', False),
                )
                logger.info("✓ Llama CPP local model initialized: %s", model_path)
            else:
                raise ValueError("Either LLAMACPP_HOST+LLAMACPP_PORT or LLAMACPP_MODEL_PATH required")
            
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}. "
                           f"Supported: ollama, openai, localai, azure, llamacpp")
        
        return llm_instance
        
    except Exception as e:
        logger.error("Failed to initialize LLM instance: %s", str(e))
        raise


# ========== DYNAMIC EMBEDDING MODEL INITIALIZATION ==========

def create_embedding_instance(provider=None, model=None, **kwargs):
    """
    Factory function to create embedding model instance dynamically based on provider.
    
    Args:
        provider (str): Model provider - 'ollama', 'openai', 'localai', 'azure', 'llamacpp'
        model (str): Model name/ID for embeddings
        **kwargs: Additional provider-specific arguments
        
    Returns:
        Embedding instance from LangChain
        
    Raises:
        ValueError: If provider is not supported
    """
    # Use defaults from config if not provided
    provider = provider or MODEL_PROVIDER
    model = EMBEDDING_MODEL
    
    logger.info("Creating embedding instance: provider=%r, model=%r", provider, model)
    
    try:
        if provider.lower() == 'ollama':
            """Ollama embeddings"""
            from langchain_community.embeddings import OllamaEmbeddings
            
            embedding_instance = OllamaEmbeddings(
                model=model,
                base_url=BASE_URL,
            )
            logger.info("✓ Ollama embeddings initialized: %s at %s", model, BASE_URL)
            
        elif provider.lower() == 'openai':
            """OpenAI embeddings"""
            from langchain_openai import OpenAIEmbeddings
            
            api_key = kwargs.get('api_key') or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")
            
            embedding_instance = OpenAIEmbeddings(
                api_key=str(api_key),  # type: ignore
                model=model,
                timeout=kwargs.get('timeout', 600),
            )
            logger.info("✓ OpenAI embeddings initialized: %s", model)
            
        elif provider.lower() == 'localai':
            """LocalAI embeddings (OpenAI-compatible)"""
            from langchain_openai import OpenAIEmbeddings
            
            base_url = kwargs.get('base_url') or os.getenv("LOCALAI_BASE_URL", "http://localhost:8080/v1")
            api_key = kwargs.get('api_key') or os.getenv("LOCALAI_API_KEY", "") or "not-needed"
            
            embedding_instance = OpenAIEmbeddings(
                api_key=str(api_key),  # type: ignore
                model=model,
                base_url=base_url,
                timeout=kwargs.get('timeout', 600),
            )
            logger.info("✓ LocalAI embeddings initialized: %s at %s", model, base_url)
            
        elif provider.lower() == 'azure':
            """Azure OpenAI embeddings"""
            from langchain_openai import AzureOpenAIEmbeddings
            
            api_key = kwargs.get('api_key') or os.getenv("AZURE_OPENAI_API_KEY")
            if not api_key:
                raise ValueError("AZURE_OPENAI_API_KEY not found")
            
            embedding_instance = AzureOpenAIEmbeddings(
                azure_endpoint=kwargs.get('azure_endpoint') or os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=str(api_key),  # type: ignore
                api_version=kwargs.get('api_version') or os.getenv("EMBEDDING_API_VERSION") or os.getenv("API_VERSION") or "2024-02-15-preview",
                model=model,
                timeout=kwargs.get('timeout', 600),
            )
            logger.info("✓ Azure OpenAI embeddings initialized: %s", model)
            
        elif provider.lower() == 'llamacpp':
            """Llama CPP embeddings (local GGUF)"""
            from langchain_community.embeddings import OpenAIEmbeddings
            
            # Llama.cpp embeddings via local ollama-like interface
            # Typically served through LM Studio or ollama with llamacpp backend
            host = kwargs.get('host') or os.getenv("LLAMACPP_HOST")
            port = kwargs.get('port') or os.getenv("LLAMACPP_PORT")
            model_path = kwargs.get('model_path') or os.getenv("LLAMACPP_MODEL_PATH")
            logger.info("Initializing Llama CPP embeddings with host=%r, port=%r, model_path=%r, model=%r", host, port, model_path, model)
            if host and port:
                # Remote embedding server
                base_url = f"http://{host}:{port}/v1"
                embedding_instance = OpenAIEmbeddings(
                    api_key="not-needed",  # type: ignore
                    model=model,
                    base_url=base_url,
                    timeout=kwargs.get('timeout', 600),
                )
                logger.info("✓ Llama CPP remote embeddings initialized: %s at %s", model, base_url)
            else:
                # Local embeddings - use fallback to ollama embeddings
                # Llama.cpp local embeddings not directly supported by LangChain
                logger.warning("Local Llama CPP embeddings not directly supported, consider using Ollama or remote server")
                raise ValueError("Llama CPP embeddings require LLAMACPP_HOST and LLAMACPP_PORT for remote server")
            
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}. "
                           f"Supported: ollama, openai, localai, azure, llamacpp")
        
        return embedding_instance
        
    except Exception as e:
        logger.error("Failed to initialize embedding instance: %s", str(e))
        raise


# ========== INITIALIZE EMBEDDING INSTANCE ==========

# Embedding instance (for RAG/vector store)
embeddings = create_embedding_instance()

# Primary LLM instance (for main analysis)
llm = create_llm_instance()

# Secondary LLM instance (for SQL generation)
sql_llm = create_llm_instance()

# Chat LLM instance
llm_chat = create_llm_instance()

# OpenAI-compatible or fallback instance
try:
    if MODEL_PROVIDER.lower() in ['localai', 'openai', 'azure']:
        openai_llm = create_llm_instance(provider=MODEL_PROVIDER)
    else:
        openai_llm = llm_chat
except Exception as e:
    logger.warning("Failed to initialize OpenAI-compatible LLM, using default: %s", str(e))
    openai_llm = llm_chat

logger.info("All LLM instances initialized successfully. Provider: %s, Model: %s",
            MODEL_PROVIDER, MODEL)


# ========== LOCAL LLM INSTANCES (Ollama — always localhost:11434) ==========
# These are initialized independently of the primary provider (Azure/OpenAI/etc.).
# If Ollama is not running, both will be None and the local chat path raises a clear error.
_LOCAL_OLLAMA_BASE_URL = "http://localhost:11434"
_LOCAL_CHAT_MODEL = os.getenv("LOCAL_MODEL", "gemma4:latest")
_LOCAL_EMBED_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "nomic-embed-text:latest")

try:
    from langchain_community.embeddings import OllamaEmbeddings as _OllamaEmbeddings
    local_llm = OllamaLLM(
        model=_LOCAL_CHAT_MODEL,
        base_url=_LOCAL_OLLAMA_BASE_URL,
        temperature=0,
        top_p=0,
    )
    local_embeddings = _OllamaEmbeddings(
        model=_LOCAL_EMBED_MODEL,
        base_url=_LOCAL_OLLAMA_BASE_URL,
    )
    logger.info(
        "✓ Local Ollama instances ready — LLM: %s, Embeddings: %s",
        _LOCAL_CHAT_MODEL, _LOCAL_EMBED_MODEL,
    )
except Exception as _local_err:
    local_llm = None
    local_embeddings = None
    logger.warning("Local Ollama unavailable (is Ollama running?): %s", _local_err)

# ---------- ROUTING DECISION ----------

routing_parser = PydanticOutputParser(pydantic_object=RoutingDecision)

routing_prompt = PromptTemplate(
    template="""
You are a routing engine for an enterprise network device migration assistant.

Actions:
- ANALYZE_FILE
- SEARCH_RAG
- DIRECT_ANSWER
- CLARIFY
- REFUSE

Rules:
- File uploaded → ANALYZE_FILE
- EOL, EOS, licensing, firmware → SEARCH_RAG
- General networking theory → DIRECT_ANSWER
- Missing device model → CLARIFY

Return JSON only.

User Query:
{query}

File Attached:
{file_attached}

{format_instructions}
""",
    input_variables=["query", "file_attached"],
    partial_variables={"format_instructions": routing_parser.get_format_instructions()},
)

def route_query(query, file_attached):
    prompt = routing_prompt.format(query=query, file_attached=file_attached)
    output = llm.invoke(prompt)
    return routing_parser.parse(output)


# ---------- SUFFICIENCY DECISION ----------

sufficiency_parser = PydanticOutputParser(pydantic_object=SufficiencyDecision)

sufficiency_prompt = PromptTemplate(
    template="""
Determine if retrieved documents contain exact lifecycle or licensing information.

If exact model match → ANSWER
If partial or outdated → SEARCH_WEB
If no relevant info → SEARCH_WEB

Return JSON only.

User Question:
{query}

Retrieved Documents:
{docs}

{format_instructions}
""",
    input_variables=["query", "docs"],
    partial_variables={"format_instructions": sufficiency_parser.get_format_instructions()},
)

def check_sufficiency(query, docs):
    prompt = sufficiency_prompt.format(query=query, docs=docs)
    output = llm.invoke(prompt)
    return sufficiency_parser.parse(output)