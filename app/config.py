import os 
from . import logger
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# env = os.getenv("ENV", 'llamacpp-remote')  # Default to 'llamacpp-remote' if ENV is not set
env = os.getenv("ENV", 'azure')  # Default to 'llamacpp-remote' if ENV is not set

env_file = f".env.{env}"

env_path = os.path.join(BASE_DIR, env_file)

logger.info("Configuration loaded for environment: %r", env)
logger.info("Loading configuration from %r", env_path)

if os.path.exists(env_path):
    logger.info("Environment file found: %r", env_path)
    load_dotenv(env_path, override=True)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
BASE_URL  = os.getenv("BASE_URL", "http://localhost:11434")
MODEL = os.getenv("MODEL", "llama3.2:3b")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama")  # Options: 'localai', 'ollama'

logger.info("Configuration - MODEL: %r, EMBEDDING_MODEL: %r, BASE_URL: %r, MODEL_PROVIDER: %r", 
            MODEL, EMBEDDING_MODEL, BASE_URL, MODEL_PROVIDER)

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "device_kb"


TEMPERATURE = 0
TOP_P = 0

MEMORY_TOP_K = 5
RAG_TOP_K = 5

RAG_INDEX_PATH = "data/rag_index"
MEMORY_BASE_PATH = "data/session_memory"

MYSQL_URI = "mysql+pymysql://root:7030594657%40Nashik@127.0.0.1:3306/inventory"

CONVERSTIONAL_MEMORY_PROMPT = """
You are an enterprise network device migration assistant.

Use ONLY the information provided.

Conversation Memory:
{memory_context}

Internal Knowledge Base:
{rag_context}

User Question:
{query}

If information is missing, clearly state it.
Do not hallucinate.
"""
